import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Miniflare, Response as WorkerResponse } from "miniflare";
import { decode, encode } from "fast-png";
import Stripe from "stripe";
import {
  bidSchema,
  dollarsToCents,
  minimumBid,
  slots,
  activeSlots,
  compareSlots,
  type AuctionSnapshot,
} from "../src/lib/auction";

const secret = "whsec_local_integration_test_only";
let mf: Miniflare;
let directory: string;
let requestNumber = 0;
const sessions = new Map<string, Record<string, unknown>>();
const sessionsByKey = new Map<string, string>();
const refunds = new Map<string, Record<string, unknown>>();
const refundRequests: string[] = [];
const image = encode({
  width: 2,
  height: 2,
  channels: 4,
  data: new Uint8Array([
    255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 0, 255, 255, 255, 255,
  ]),
});

beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), "drivingfly-test-"));
  const script = join(directory, "worker.mjs");
  await build({
    entryPoints: ["worker/api.ts"],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    outfile: script,
    external: ["cloudflare:workers", "node:*"],
  });
  const outboundService: NonNullable<
    ConstructorParameters<typeof Miniflare>[0]["outboundService"]
  > = async (request: import("miniflare").Request) => {
    const url = new URL(request.url);
    if (url.origin !== "https://api.stripe.com")
      throw new Error(`Unexpected outbound request to ${url.origin}`);
    if (url.pathname === "/v1/checkout/sessions" && request.method === "POST") {
      const form = new URLSearchParams(await request.text());
      const key = request.headers.get("Idempotency-Key")!;
      expect(key).toMatch(/^checkout:/);
      let id = sessionsByKey.get(key);
      if (!id) {
        id = `cs_test_${sessions.size + 1}`;
        sessionsByKey.set(key, id);
        sessions.set(id, {
          id,
          object: "checkout.session",
          mode: "payment",
          status: "open",
          payment_status: "unpaid",
          currency: "usd",
          amount_total: Number(
            form.get("line_items[0][price_data][unit_amount]"),
          ),
          client_reference_id: form.get("client_reference_id"),
          metadata: { bid_id: form.get("metadata[bid_id]") },
          livemode: false,
          payment_intent: `pi_${id}`,
          url: `https://checkout.stripe.com/c/pay/${id}`,
        });
      }
      return WorkerResponse.json(sessions.get(id));
    }
    if (/\/v1\/checkout\/sessions\/cs_test_\d+$/.test(url.pathname))
      return WorkerResponse.json(sessions.get(url.pathname.split("/").at(-1)!));
    if (url.pathname === "/v1/refunds" && request.method === "POST") {
      const form = new URLSearchParams(await request.text());
      const payment = form.get("payment_intent")!;
      refundRequests.push(payment);
      const refund = {
        id: `re_${payment}`,
        object: "refund",
        status: "succeeded",
        payment_intent: payment,
      };
      refunds.set(refund.id, refund);
      return WorkerResponse.json(refund);
    }
    if (/\/v1\/refunds\/re_.+$/.test(url.pathname))
      return WorkerResponse.json(refunds.get(url.pathname.split("/").at(-1)!));
    throw new Error(
      `Unexpected Stripe request: ${request.method} ${url.pathname}`,
    );
  };
  mf = new Miniflare({
    modules: true,
    modulesRoot: directory,
    scriptPath: script,
    compatibilityDate: "2026-07-30",
    compatibilityFlags: ["nodejs_compat"],
    durableObjects: { AUCTION: { className: "Auction", useSQLite: true } },
    r2Buckets: ["ARTWORK"],
    outboundService,
    bindings: {
      SITE_URL: "http://localhost:3000",
      STRIPE_API_KEY: "sk_test_local_test_only",
      STRIPE_WEBHOOK_SECRET: secret,
    },
  });
  await mf.ready;
}, 30_000);
afterAll(async () => {
  await mf?.dispose();
  if (directory) await rm(directory, { recursive: true, force: true });
});

function request(
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
) {
  return mf.dispatchFetch(`http://localhost:3000${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Origin: "http://localhost:3000",
      "CF-Connecting-IP": `192.0.2.${++requestNumber}`,
      "Content-Type": "application/json",
      ...headers,
    },
    body:
      body === undefined
        ? undefined
        : body instanceof Uint8Array
          ? body
          : JSON.stringify(body),
  });
}
async function upload(png = image) {
  const response = await request("/api/artwork", png, {
    "Content-Type": "image/png",
  });
  expect(response.status).toBe(201);
  return ((await response.json()) as { token: string }).token;
}
async function bid(slotId: string, amount: number, brand = "Test studio") {
  const artworkToken = await upload();
  const logoToken = await upload();
  const input = {
    requestId: crypto.randomUUID(),
    slotId,
    amount,
    brand,
    message: "Independent ideas, made with care.",
    url: "https://example.com",
    artworkToken,
    logoToken,
    acceptedTerms: true,
  };
  const response = await request("/api/checkout", input);
  expect(response.status).toBe(200);
  return { ...((await response.json()) as { sessionId: string }), input };
}
async function pay(sessionId: string) {
  const session = sessions.get(sessionId)!;
  session.status = "complete";
  session.payment_status = "paid";
  const payload = JSON.stringify({
    id: `evt_${crypto.randomUUID()}`,
    object: "event",
    type: "checkout.session.completed",
    data: { object: session },
  });
  const signature = Stripe.webhooks.generateTestHeaderString({
    payload,
    secret,
  });
  return mf.dispatchFetch("http://localhost:3000/api/stripe/webhook", {
    method: "POST",
    body: payload,
    headers: { "Stripe-Signature": signature },
  });
}
async function snapshot() {
  return (await (await request("/api/auction")).json()) as AuctionSnapshot;
}

describe("auction rules", () => {
  it("balances the larger layout and preserves paid artwork proportions", () => {
    const current = activeSlots({});
    const counts = Object.fromEntries(
      ["left", "right", "top", "front", "back"].map((face) => [
        face,
        current.filter((s) => s.face === face).length,
      ]),
    );
    expect(counts).toEqual({ left: 3, right: 3, top: 2, front: 2, back: 2 });
    const previous: Record<string, [number, number]> = {
      "ad-01": [1.08, 0.29],
      "ad-10": [0.6, 0.23],
      "ad-16": [1.08, 0.29],
      "ad-25": [0.6, 0.23],
      "ad-31": [0.66, 0.22],
      "ad-38": [0.82, 0.64],
      "ad-48": [0.86, 0.115],
      "ad-53": [0.4, 0.12],
      "ad-54": [0.88, 0.22],
      "ad-56": [0.34, 0.11],
      "ad-57": [0.34, 0.11],
      "ad-59": [0.46, 0.09],
    };
    for (const slot of current) {
      const [width, height] = previous[slot.id];
      expect(slot.width_m * slot.height_m).toBeGreaterThan(width * height);
      if (
        ["ad-01", "ad-53", "ad-54", "ad-56", "ad-57", "ad-59"].includes(slot.id)
      )
        expect(slot.width_m / slot.height_m).toBeCloseTo(width / height, 6);
    }
  });
  it("offers twelve spots and preserves purchases outside the preferred inventory", () => {
    const placement = (slotId: string) => ({
      id: slotId,
      slotId,
      brand: "Existing sponsor",
      message: "",
      url: "https://example.com",
      amount: 100,
      textureUrl: "/art.png",
      logoUrl: "/logo.png",
      publishedAt: 1,
    });
    const placements = Object.fromEntries(
      ["ad-01", "ad-53", "ad-54", "ad-56", "ad-57", "ad-59", "ad-02"].map(
        (id) => [id, placement(id)],
      ),
    );
    const active = activeSlots(placements);
    expect(active).toHaveLength(12);
    expect(active.map((slot) => slot.id)).toEqual(
      expect.arrayContaining(Object.keys(placements)),
    );
    const ordered = active.sort((a, b) => compareSlots(a, b, placements));
    expect(ordered.slice(0, 7).map((s) => s.id)).toEqual([
      "ad-01",
      "ad-56",
      "ad-57",
      "ad-53",
      "ad-54",
      "ad-59",
      "ad-02",
    ]);
    expect(ordered.slice(7).map((s) => s.id)).toEqual([
      "ad-10",
      "ad-16",
      "ad-31",
      "ad-38",
      "ad-48",
    ]);
    expect(activeSlots({})).toHaveLength(12);
    // Honouring existing payments takes priority even if more than twelve legacy spots sold.
    const legacy = Object.fromEntries(
      slots.slice(0, 13).map((s) => [s.id, placement(s.id)]),
    );
    expect(activeSlots(legacy)).toHaveLength(13);
  });
  it("rejects new checkouts for retired geometry IDs before contacting Stripe", async () => {
    const before = sessions.size;
    const response = await request("/api/checkout", {
      requestId: crypto.randomUUID(),
      slotId: "ad-02",
      amount: 100,
      brand: "Retired",
      message: "",
      url: "https://example.com",
      artworkToken: crypto.randomUUID(),
      logoToken: crypto.randomUUID(),
      acceptedTerms: true,
    });
    expect(response.status).toBe(409);
    expect(await response.text()).toContain("retired");
    expect(sessions.size).toBe(before);
    expect((await snapshot()).activeSlotIds).toHaveLength(12);
  });
  it("uses cents without floating point errors and requires a full dollar increment", () => {
    expect(dollarsToCents("1.01")).toBe(101);
    expect(dollarsToCents("1.001")).toBeNull();
    expect(dollarsToCents("1e3")).toBeNull();
    expect(dollarsToCents("-2")).toBeNull();
    expect(minimumBid()).toBe(100);
    expect(minimumBid(123)).toBe(223);
    expect(slots).toHaveLength(59);
    expect(new Set(slots.map((s) => s.id)).size).toBe(59);
  });
  it("rejects unsafe links and unknown slot ids", () => {
    const base = {
      requestId: crypto.randomUUID(),
      amount: 100,
      brand: "Test",
      message: "",
      artworkToken: crypto.randomUUID(),
      logoToken: crypto.randomUUID(),
      acceptedTerms: true,
    };
    expect(
      bidSchema.safeParse({
        ...base,
        slotId: "ad-01",
        url: "javascript:alert(1)",
      }).success,
    ).toBe(false);
    expect(
      bidSchema.safeParse({
        ...base,
        slotId: "ad-09",
        url: "https://example.com",
      }).success,
    ).toBe(false);
  });
  it("starts empty and keeps uploads private until a verified purchase", async () => {
    expect((await snapshot()).totalRaised).toBe(0);
    const token = await upload();
    expect((await request(`/api/artwork/${token}.png`)).status).toBe(404);
    expect(
      (
        await request(
          "/api/artwork",
          new TextEncoder().encode("<svg><script/></svg>"),
        )
      ).status,
    ).toBe(400);
  });
  it("rejects cross-origin checkout and forged webhook signatures", async () => {
    expect(
      (await request("/api/checkout", {}, { Origin: "https://evil.example" }))
        .status,
    ).toBe(403);
    expect(
      (
        await request(
          "/api/stripe/webhook",
          {},
          { "Stripe-Signature": "invalid" },
        )
      ).status,
    ).toBe(400);
    expect((await snapshot()).revision).toBe(0);
  });
  it("publishes only after payment, serves immutable artwork, and broadcasts the livery", async () => {
    const result = await bid("ad-01", 100);
    expect(
      (await request(`/api/artwork/${result.input.logoToken}.png`)).status,
    ).toBe(404);
    const pending = await request("/api/checkout/confirm", {
      sessionId: result.sessionId,
    });
    expect(((await pending.json()) as { status: string }).status).toBe(
      "pending",
    );
    expect((await snapshot()).placements["ad-01"]).toBeUndefined();
    const wsResponse = await request("/api/live", undefined, {
      Upgrade: "websocket",
    });
    const socket = wsResponse.webSocket!;
    socket.accept();
    const pushed = new Promise<AuctionSnapshot>((resolve) =>
      socket.addEventListener("message", (event) => {
        const data = JSON.parse(String(event.data));
        if (data.revision === 1) resolve(data);
      }),
    );
    expect((await pay(result.sessionId)).status).toBe(200);
    const live = await pushed;
    expect(live.placements["ad-01"].amount).toBe(100);
    expect(live.placements["ad-01"].message).toBe(result.input.message);
    expect(live.history[0].message).toBe(result.input.message);
    expect(live.placements["ad-01"].logoUrl).not.toBe(
      live.placements["ad-01"].textureUrl,
    );
    const logo = await request(live.placements["ad-01"].logoUrl);
    expect(logo.status).toBe(200);
    expect(logo.headers.get("Cache-Control")).toContain("immutable");
    expect(decode(new Uint8Array(await logo.arrayBuffer())).data).toEqual(
      decode(image).data,
    );
    expect(live.totalRaised).toBe(100);
    const artwork = await request(live.placements["ad-01"].textureUrl);
    expect(artwork.status).toBe(200);
    expect(artwork.headers.get("Cache-Control")).toContain("immutable");
    const servedPng = new Uint8Array(await artwork.arrayBuffer());
    expect(decode(servedPng).data).toEqual(decode(image).data);
    expect(servedPng.slice(0, 8)).toEqual(image.slice(0, 8));
    socket.close();
  });
  it("deduplicates checkout retries and payment redelivery", async () => {
    const result = await bid("ad-16", 200);
    const repeat = await request("/api/checkout", result.input);
    expect(((await repeat.json()) as { sessionId: string }).sessionId).toBe(
      result.sessionId,
    );
    expect(
      (
        await request("/api/checkout", {
          ...result.input,
          message: "Changed after checkout",
        })
      ).status,
    ).toBe(409);
    expect(
      (
        await request("/api/checkout", {
          ...result.input,
          logoToken: crypto.randomUUID(),
        })
      ).status,
    ).toBe(409);
    await pay(result.sessionId);
    const before = await snapshot();
    await pay(result.sessionId);
    const after = await snapshot();
    expect(after.revision).toBe(before.revision);
    expect(after.totalRaised).toBe(before.totalRaised);
  });
  it("rejects bids less than one dollar above the current owner before checkout", async () => {
    const token = await upload();
    const result = await request("/api/checkout", {
      requestId: crypto.randomUUID(),
      slotId: "ad-01",
      amount: 199,
      brand: "Late",
      message: "",
      url: "https://example.com",
      artworkToken: token,
      logoToken: token,
      acceptedTerms: true,
    });
    expect(result.status).toBe(409);
    expect(await result.text()).toContain("$2");
  });
  it("refunds checkouts that no longer meet the dollar increment, exactly once", async () => {
    const low = await bid("ad-31", 100, "Low");
    const equal = await bid("ad-31", 500, "Equal");
    const insufficient = await bid("ad-31", 599, "Less than a dollar higher");
    const high = await bid("ad-31", 500, "High");
    await pay(high.sessionId);
    await Promise.all([
      pay(low.sessionId),
      pay(equal.sessionId),
      pay(insufficient.sessionId),
    ]);
    const live = await snapshot();
    expect(live.placements["ad-31"].brand).toBe("High");
    expect(live.history.filter((p) => p.slotId === "ad-31")).toHaveLength(1);
    for (const loser of [low, equal, insufficient]) {
      const status = await request("/api/checkout/confirm", {
        sessionId: loser.sessionId,
      });
      expect(((await status.json()) as { status: string }).status).toBe(
        "refunded",
      );
      await pay(loser.sessionId);
      expect(
        refundRequests.filter((p) => p === `pi_${loser.sessionId}`),
      ).toHaveLength(1);
    }
  });
  it("replaces a published ad with a higher one, retaining support history without refunding the first", async () => {
    const before = await snapshot();
    const first = before.placements["ad-01"];
    const next = await bid("ad-01", 200, "Next studio");
    await pay(next.sessionId);
    const live = await snapshot();
    expect(live.placements["ad-01"].id).not.toBe(first.id);
    expect(live.placements["ad-01"].textureUrl).not.toBe(first.textureUrl);
    expect(live.history.some((p) => p.id === first.id)).toBe(true);
    expect(live.totalRaised).toBe(before.totalRaised + 200);
    expect(refundRequests).toHaveLength(3);
  });
  it("does not publish a paid session with a mismatched amount", async () => {
    const result = await bid("ad-38", 100);
    sessions.get(result.sessionId)!.amount_total = 99;
    expect((await pay(result.sessionId)).status).toBe(400);
    expect((await snapshot()).placements["ad-38"]).toBeUndefined();
  });
  it("validates messages and requires an unclaimed logo upload before checkout", async () => {
    const artworkToken = await upload();
    const input = {
      requestId: crypto.randomUUID(),
      slotId: "ad-48",
      amount: 100,
      brand: "Studio",
      url: "https://example.com",
      message: "",
      artworkToken,
      logoToken: crypto.randomUUID(),
      acceptedTerms: true,
    };
    expect(
      bidSchema.parse({ ...input, message: "  Made with care.  " }).message,
    ).toBe("Made with care.");
    expect(
      bidSchema.safeParse({ ...input, message: "a".repeat(140) }).success,
    ).toBe(true);
    expect(
      (await request("/api/checkout", { ...input, message: "a".repeat(141) }))
        .status,
    ).toBe(400);
    expect((await request("/api/checkout", input)).status).toBe(400);
    const takenLogo = (await snapshot()).placements["ad-01"].logoUrl
      .split("/")
      .at(-1)!
      .replace(".png", "");
    expect(
      (await request("/api/checkout", { ...input, logoToken: takenLogo }))
        .status,
    ).toBe(400);
    const logoToken = await upload();
    expect(
      (await request("/api/checkout", { ...input, logoToken })).status,
    ).toBe(200);
  });
});
