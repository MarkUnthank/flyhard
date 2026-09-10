import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  Miniflare,
  kCurrentWorker,
  Response as WorkerResponse,
} from "miniflare";
import { decode, encode } from "fast-png";
import Stripe from "stripe";
import {
  WRAP_BOOKING_URL,
  WRAP_TEXTURE_URL,
} from "../worker/custom-wrap-email";
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
let mfOptions: ConstructorParameters<typeof Miniflare>[0];
let directory: string;
let requestNumber = 0;
const sessions = new Map<string, Record<string, unknown>>();
const sessionsByKey = new Map<string, string>();
const checkoutForms = new Map<string, URLSearchParams>();
const refunds = new Map<string, Record<string, unknown>>();
const refundRequests: string[] = [];
const emails: EmailMessageBuilder[] = [];
let failEmail = false;
let failEmailAudience: string | undefined;
let testMode = false;
let failSessionRead: string | undefined;
let sessionReads: string[] = [];
type TestStub = {
  testSql(
    query: string,
    ...values: (string | number | null)[]
  ): Promise<Record<string, unknown>[]>;
  testAlarm(): Promise<number | null>;
  testConfig(test: boolean, recipient?: string): Promise<void>;
  testWrapConfig(recipient?: string, testRecipient?: string): Promise<void>;
};
let testStub: TestStub;
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
    entryPoints: ["tests/fixtures/auction-worker.ts"],
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
    if (url.origin === "https://email.test") {
      const message = (await request.json()) as EmailMessageBuilder;
      if (
        failEmail ||
        (failEmailAudience &&
          message.headers?.["X-Custom-Wrap-Audience"] === failEmailAudience)
      )
        return new WorkerResponse("Temporary failure", { status: 503 });
      emails.push(message);
      return WorkerResponse.json({ messageId: `email-${emails.length}` });
    }
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
        checkoutForms.set(id, form);
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
          metadata: form.has("metadata[custom_wrap_order_id]")
            ? {
                custom_wrap_order_id: form.get(
                  "metadata[custom_wrap_order_id]",
                ),
              }
            : { bid_id: form.get("metadata[bid_id]") },
          custom_fields: [
            { key: "brand", type: "text", text: { value: "Wrap test studio" } },
          ],
          livemode: !testMode,
          customer_details: { email: `${id}@example.test` },
          payment_intent: `pi_${id}`,
          url: `https://checkout.stripe.com/c/pay/${id}`,
        });
      }
      return WorkerResponse.json(sessions.get(id));
    }
    if (url.pathname === "/v1/checkout/sessions" && request.method === "GET") {
      const all = [...sessions.values()];
      const start = url.searchParams.get("starting_after");
      const remaining = start
        ? all.slice(all.findIndex((s) => s.id === start) + 1)
        : all;
      const data = remaining.slice(0, 3);
      return WorkerResponse.json({
        object: "list",
        url: "/v1/checkout/sessions",
        data,
        has_more: remaining.length > data.length,
      });
    }
    if (/\/v1\/checkout\/sessions\/cs_test_\d+$/.test(url.pathname)) {
      const id = url.pathname.split("/").at(-1)!;
      sessionReads.push(id);
      if (id === failSessionRead)
        return WorkerResponse.json(
          { error: { type: "api_error", message: "Temporary Stripe failure" } },
          { status: 503 },
        );
      return WorkerResponse.json(sessions.get(id));
    }
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
  mfOptions = {
    name: "auction-test",
    durableObjectsPersist: join(directory, "do"),
    r2Persist: join(directory, "r2"),
    modules: true,
    modulesRoot: directory,
    scriptPath: script,
    compatibilityDate: "2026-07-30",
    compatibilityFlags: ["nodejs_compat"],
    durableObjects: { AUCTION: { className: "Auction", useSQLite: true } },
    r2Buckets: ["ARTWORK"],
    outboundService,
    serviceBindings: {
      EMAIL: { name: kCurrentWorker, entrypoint: "TestEmail" },
    },
    bindings: {
      SITE_URL: "http://localhost:3000",
      AUCTION_ADMIN_TOKEN: "admin_credit_test_only",
      STRIPE_API_KEY: "local_live_fixture",
      OUTBID_EMAIL_FROM: "updates@notify.example.test",
      CUSTOM_WRAP_EMAIL_TO: "operator@example.test",
      STRIPE_WEBHOOK_SECRET: secret,
    },
  };
  mf = new Miniflare(mfOptions);
  await mf.ready;
  const namespace = await mf.getDurableObjectNamespace("AUCTION");
  testStub = namespace.get(
    namespace.idFromName("the-driving-fly-v1"),
  ) as unknown as TestStub;
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
  it("keeps seven large panels and Supertask on the rear window", () => {
    const current = activeSlots({});
    const counts = Object.fromEntries(
      ["left", "right", "top", "front", "back"].map((face) => [
        face,
        current.filter((s) => s.face === face).length,
      ]),
    );
    expect(counts).toEqual({ left: 3, right: 1, top: 1, front: 1, back: 1 });
    const previous: Record<string, [number, number]> = {
      "ad-01": [1.38, 0.3705555556],
      "ad-10": [1.08, 0.31],
      "ad-53": [1.1, 0.33],
      "ad-54": [1.24, 0.31],
      "ad-56": [0.7, 0.2264705882],
      "ad-57": [0.7, 0.2264705882],
      "ad-59": [1.12, 0.2191304348],
    };
    for (const slot of current) {
      const [width, height] = previous[slot.id];
      expect(slot.width_m * slot.height_m).toBeGreaterThanOrEqual(
        width * height - 1e-9,
      );
    }
    expect(current.find((s) => s.id === "ad-54")?.face).toBe("back");
    expect(current.find((s) => s.id === "ad-57")).toMatchObject({
      width_m: 1.1,
      height_m: 0.68,
    });
    expect(current.find((s) => s.id === "ad-59")).toMatchObject({
      width_m: 1.3532,
      height_m: 0.3587,
    });
  });
  it("offers seven spots and preserves purchases outside the preferred inventory", () => {
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
    expect(active).toHaveLength(7);
    expect(active.map((slot) => slot.id)).toEqual(
      expect.arrayContaining(Object.keys(placements)),
    );
    const ordered = active.sort((a, b) => compareSlots(a, b, placements));
    expect(ordered.slice(0, 7).map((s) => s.id)).toEqual([
      "ad-01",
      "ad-56",
      "ad-57",
      "ad-59",
      "ad-53",
      "ad-54",
      "ad-02",
    ]);
    expect(ordered.slice(7)).toEqual([]);
    expect(activeSlots({})).toHaveLength(7);
    // Honouring existing payments takes priority even if more than seven legacy spots sold.
    const legacy = Object.fromEntries(
      slots.slice(0, 13).map((s) => [s.id, placement(s.id)]),
    );
    expect(activeSlots(legacy)).toHaveLength(13);
  });
  it.each(["ad-02", "ad-16", "ad-25", "ad-31", "ad-38", "ad-48"])(
    "rejects new checkout for retired %s before contacting Stripe",
    async (retiredId) => {
      const before = sessions.size;
      const response = await request("/api/checkout", {
        requestId: crypto.randomUUID(),
        slotId: retiredId,
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
      expect((await snapshot()).activeSlotIds).toHaveLength(7);
    },
  );
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
    const result = await bid("ad-10", 200);
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
    const low = await bid("ad-53", 100, "Low");
    const equal = await bid("ad-53", 500, "Equal");
    const insufficient = await bid("ad-53", 599, "Less than a dollar higher");
    const high = await bid("ad-53", 500, "High");
    await pay(high.sessionId);
    await Promise.all([
      pay(low.sessionId),
      pay(equal.sessionId),
      pay(insufficient.sessionId),
    ]);
    const live = await snapshot();
    expect(live.placements["ad-53"].brand).toBe("High");
    expect(live.history.filter((p) => p.slotId === "ad-53")).toHaveLength(1);
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
    const {
      paidAmount: _paid,
      complimentaryCredit: _credit,
      ...originalPaidBid
    } = first;
    expect(live.highestBids.find((p) => p.id === first.id)).toEqual(
      originalPaidBid,
    );
    expect(live.highestBids.map((p) => p.amount)).toEqual(
      live.highestBids.map((p) => p.amount).sort((a, b) => b - a),
    );
    expect(live.totalRaised).toBe(before.totalRaised + 200);
    expect(refundRequests).toHaveLength(3);
  });
  it("does not publish a paid session with a mismatched amount", async () => {
    const result = await bid("ad-54", 100);
    sessions.get(result.sessionId)!.amount_total = 99;
    expect((await pay(result.sessionId)).status).toBe(400);
    expect((await snapshot()).placements["ad-54"]).toBeUndefined();
  });
  it("validates messages and requires an unclaimed logo upload before checkout", async () => {
    const artworkToken = await upload();
    const input = {
      requestId: crypto.randomUUID(),
      slotId: "ad-56",
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

describe("outbid notifications", () => {
  it("emails only the displaced owner, once across concurrent webhook redelivery", async () => {
    // The earlier tests include unpaid, mismatched and refund-race checkouts.
    await expect.poll(() => emails.length).toBe(1);
    const first = emails[0];
    expect(first.to).toBe("cs_test_1@example.test");
    expect(first.text).toContain("confirmed $2 bid");
    expect(first.text).toContain("starts at $3 USD");
    expect(first.html).toContain("?spot=ad-01");
    expect(first.subject).not.toContain("[TEST]");
    const winner = [...sessions.values()].find(
      (s) =>
        (s.metadata as { bid_id: string }).bid_id ===
        first.headers!["X-Outbid-Notification"],
    );
    expect(winner).toBeDefined();
    const current = (await snapshot()).placements["ad-01"];
    const currentSession = [...sessions.values()].find(
      (s) => s.client_reference_id === current.id,
    )!;
    await Promise.all([
      pay(String(currentSession.id)),
      pay(String(currentSession.id)),
    ]);
    await testStub.testAlarm();
    expect(emails).toHaveLength(1);
    const data = JSON.stringify(await snapshot());
    expect(data).not.toContain("@example.test");
    expect(data).not.toContain("buyer_email");
    expect(data).not.toContain("session_id");
    expect(data).not.toContain("message_id");
  });

  it("recovers existing sponsors' addresses from Stripe and retries email without blocking publication", async () => {
    const owner = (await snapshot()).placements["ad-10"];
    await testStub.testSql(
      "UPDATE bids SET buyer_email = NULL WHERE id = ?",
      owner.id,
    );
    sessionReads = [];
    failEmail = true;
    const replacement = await bid("ad-10", 300, "Replacement");
    expect((await pay(replacement.sessionId)).status).toBe(200);
    expect((await snapshot()).placements["ad-10"].amount).toBe(300);
    await expect
      .poll(
        async () =>
          (
            await testStub.testSql(
              "SELECT attempts FROM outbid_emails WHERE previous_bid_id = ?",
              owner.id,
            )
          )[0]?.attempts,
      )
      .toBe(1);
    expect(sessionReads).toContain("cs_test_2");
    expect(emails).toHaveLength(1);
    expect(await testStub.testAlarm()).not.toBeNull();
    // The queue persists; make its next attempt due without waiting a minute.
    failEmail = false;
    await testStub.testSql(
      "UPDATE outbid_emails SET next_attempt_at = 0 WHERE previous_bid_id = ?",
      owner.id,
    );
    await testStub.testAlarm();
    expect(emails).toHaveLength(2);
    expect(emails[1].to).toBe("cs_test_2@example.test");
    expect(
      await testStub.testSql(
        "SELECT status, attempts, message_id FROM outbid_emails WHERE previous_bid_id = ?",
        owner.id,
      ),
    ).toEqual([{ status: "sent", attempts: 2, message_id: "email-2" }]);
    await pay(replacement.sessionId);
    await testStub.testAlarm();
    expect(emails).toHaveLength(2);
  });

  it("does not notify an owner who raises their own bid", async () => {
    const owner = (await snapshot()).placements["ad-10"];
    const session = [...sessions.values()].find(
      (s) => s.client_reference_id === owner.id,
    )!;
    const replacement = await bid("ad-10", 400, "Same owner");
    sessions.get(replacement.sessionId)!.customer_details =
      session.customer_details;
    await pay(replacement.sessionId);
    await expect
      .poll(
        async () =>
          (
            await testStub.testSql(
              "SELECT status FROM outbid_emails WHERE previous_bid_id = ?",
              owner.id,
            )
          )[0]?.status,
      )
      .toBe("skipped");
    expect(emails).toHaveLength(2);
  });

  it("fails visibly for a missing Stripe email without affecting the new winner", async () => {
    const owner = (await snapshot()).placements["ad-10"];
    const session = [...sessions.values()].find(
      (s) => s.client_reference_id === owner.id,
    )!;
    session.customer_details = null;
    await testStub.testSql(
      "UPDATE bids SET buyer_email = NULL WHERE id = ?",
      owner.id,
    );
    const replacement = await bid("ad-10", 500);
    await pay(replacement.sessionId);
    await expect
      .poll(
        async () =>
          (
            await testStub.testSql(
              "SELECT last_error FROM outbid_emails WHERE previous_bid_id = ?",
              owner.id,
            )
          )[0]?.last_error,
      )
      .toBe("E_NO_CHECKOUT_EMAIL");
    expect((await snapshot()).placements["ad-10"].amount).toBe(500);
    expect(emails).toHaveLength(2);
  });

  it("keeps the email alarm alive and resumes pending delivery after a runtime restart", async () => {
    const owner = (await snapshot()).placements["ad-10"];
    // Remove unrelated abandoned-upload work so the email alone must keep the alarm alive.
    await testStub.testSql(
      "DELETE FROM uploads WHERE bid_id IS NULL OR bid_id IN (SELECT id FROM bids WHERE status IN ('pending','refund_pending','expired'))",
    );
    failEmail = true;
    const replacement = await bid("ad-10", 600);
    await pay(replacement.sessionId);
    await expect
      .poll(
        async () =>
          (
            await testStub.testSql(
              "SELECT attempts FROM outbid_emails WHERE previous_bid_id = ?",
              owner.id,
            )
          )[0]?.attempts,
      )
      .toBe(1);
    expect(await testStub.testAlarm()).not.toBeNull();
    await mf.dispose();
    mf = new Miniflare(mfOptions);
    await mf.ready;
    const ns = await mf.getDurableObjectNamespace("AUCTION");
    testStub = ns.get(
      ns.idFromName("the-driving-fly-v1"),
    ) as unknown as TestStub;
    failEmail = false;
    await testStub.testSql(
      "UPDATE outbid_emails SET next_attempt_at = 0 WHERE previous_bid_id = ?",
      owner.id,
    );
    await testStub.testAlarm();
    expect(emails).toHaveLength(3);
    await pay(replacement.sessionId);
    await testStub.testAlarm();
    expect(emails).toHaveLength(3);
  });

  it("routes all sandbox email to the configured test recipient and fails closed without one", async () => {
    testMode = true;
    await testStub.testConfig(true);
    const first = await bid("ad-59", 100);
    const second = await bid("ad-59", 200);
    await pay(first.sessionId);
    await pay(second.sessionId);
    await testStub.testAlarm();
    expect(emails).toHaveLength(3);
    await testStub.testConfig(true, "operator@example.test");
    await testStub.testAlarm();
    expect(emails).toHaveLength(4);
    expect(emails[3].to).toBe("operator@example.test");
    expect(emails[3].subject).toMatch(/^\[TEST\]/);
    expect(emails[3].text).toContain("No live ad was replaced");
    testMode = false;
    await testStub.testConfig(false);
  });
  it("keeps old high bids beyond recent history, preserves links, and excludes unpaid bids", async () => {
    const ids: string[] = [];
    const insert = async (
      id: string,
      amount: number,
      publishedAt: number | null,
    ) => {
      ids.push(id);
      await testStub.testSql(
        "INSERT INTO bids (id, request_id, slot_id, amount, brand, url, artwork_token, logo_token, created_at, published_at, status) VALUES (?, ?, 'ad-01', ?, 'Historical supporter', ?, 'history-artwork', 'history-logo', 1, ?, ?)",
        id,
        id,
        amount,
        "https://example.com/original?ref=sponsor",
        publishedAt,
        publishedAt === null ? "pending" : "outbid",
      );
    };
    try {
      await insert("history-old-b", 9000, 1);
      await insert("history-old-a", 9000, 1);
      for (let i = 0; i < 55; i++)
        await insert(`history-recent-${i}`, 500, Date.now() + i);
      await insert("history-unpaid", 999999, null);
      const live = await snapshot();
      expect(live.history.some((p) => p.id === "history-old-a")).toBe(false);
      expect(live.highestBids).toHaveLength(50);
      expect(live.highestBids.slice(0, 2).map((p) => p.id)).toEqual([
        "history-old-a",
        "history-old-b",
      ]);
      expect(live.highestBids[0]).toMatchObject({
        amount: 9000,
        url: "https://example.com/original?ref=sponsor",
        logoUrl: "/api/artwork/history-logo.png",
      });
      expect(live.highestBids.some((p) => p.id === "history-unpaid")).toBe(
        false,
      );
      expect(
        live.highestBids.every(
          (p) => !("buyer_email" in p) && !("session_id" in p),
        ),
      ).toBe(true);
    } finally {
      for (const id of ids)
        await testStub.testSql("DELETE FROM bids WHERE id = ?", id);
    }
  });
});

describe("complimentary sponsor credits", () => {
  it("preserves payments, rejects unauthorized/stale changes, and enforces boosted bids", async () => {
    testMode = false;
    await testStub.testConfig(false);
    const id = crypto.randomUUID();
    await testStub.testSql(
      "INSERT INTO bids (id,request_id,slot_id,amount,brand,url,artwork_token,logo_token,status,created_at,published_at) VALUES (?,?,?,200,?,?,?,?, 'published',?,?)",
      id,
      crypto.randomUUID(),
      "ad-59",
      "Credit recipient",
      "https://example.com",
      "credit-art",
      "credit-logo",
      Date.now(),
      Date.now(),
    );
    await testStub.testSql(
      "INSERT OR REPLACE INTO placements VALUES (?,?)",
      "ad-59",
      id,
    );
    const pending = await bid("ad-59", 300);
    const before = await snapshot();
    const body = {
      requestId: crypto.randomUUID(),
      bidId: id,
      expectedAmount: 200,
      credit: 400,
      reason: "Owner-authorized complimentary boost",
    };
    const auth = { Authorization: "Bearer admin_credit_test_only" };
    expect((await request("/api/admin/credits", body)).status).toBe(403);
    expect(
      (await request("/api/admin/credits", { ...body, credit: -1 }, auth))
        .status,
    ).toBe(400);
    expect(
      (
        await request(
          "/api/admin/credits",
          { ...body, expectedAmount: 300 },
          auth,
        )
      ).status,
    ).toBe(409);
    expect((await request("/api/admin/credits", body, auth)).status).toBe(200);
    const boosted = await snapshot();
    expect(boosted.placements["ad-59"]).toMatchObject({
      id,
      amount: 600,
      paidAmount: 200,
      complimentaryCredit: 400,
    });
    expect(boosted.totalRaised).toBe(before.totalRaised);
    expect(boosted.totalPurchases).toBe(before.totalPurchases);
    expect(boosted.history.find((p) => p.id === id)?.amount).toBe(200);
    expect(boosted.highestBids.find((p) => p.id === id)?.amount).toBe(200);
    expect(boosted.revision).toBe(before.revision + 1);
    expect((await request("/api/admin/credits", body, auth)).status).toBe(200);
    expect((await snapshot()).revision).toBe(boosted.revision);
    expect(
      (await request("/api/admin/credits", { ...body, credit: 500 }, auth))
        .status,
    ).toBe(409);
    expect(
      (
        await request("/api/checkout", {
          ...pending.input,
          requestId: crypto.randomUUID(),
        })
      ).status,
    ).toBe(409);
    expect((await pay(pending.sessionId)).status).toBe(200);
    expect((await snapshot()).placements["ad-59"].id).toBe(id);
    const replacement = await bid("ad-59", 700);
    expect((await pay(replacement.sessionId)).status).toBe(200);
    const after = await snapshot();
    expect(after.placements["ad-59"]).toMatchObject({
      amount: 700,
      paidAmount: 700,
      complimentaryCredit: 0,
    });
    expect(after.totalRaised).toBe(before.totalRaised + 700);
    expect(
      (
        await request(
          "/api/admin/credits",
          { ...body, requestId: crypto.randomUUID(), expectedAmount: 600 },
          auth,
        )
      ).status,
    ).toBe(409);
  });
});

async function wrapCheckout(amount?: number) {
  const input = {
    requestId: crypto.randomUUID(),
    amount: amount ?? (await snapshot()).customWrap.amount,
    acceptedTerms: true,
  };
  const response = await request("/api/custom-wrap/checkout", input);
  expect(response.status).toBe(200);
  return { ...((await response.json()) as { sessionId: string }), input };
}
const wrapEmails = () =>
  emails.filter(
    (mail) => mail.headers?.["X-Custom-Wrap-Audience"] === "operator",
  );
const wrapBuyerEmails = () =>
  emails.filter((mail) => mail.headers?.["X-Custom-Wrap-Audience"] === "buyer");

describe("custom wrap purchases", () => {
  beforeEach(async () => {
    failEmail = false;
    failEmailAudience = undefined;
    testMode = false;
    await testStub.testConfig(false);
    await testStub.testWrapConfig("operator@example.test");
    await testStub.testAlarm();
    await testStub.testSql("DELETE FROM wrap_notifications");
    await testStub.testSql("DELETE FROM wrap_orders");
    emails.length = 0;
  });
  it("starts at $10,000 with immediate capture, two videos and immutable retries", async () => {
    expect((await snapshot()).customWrap).toEqual({
      amount: 1_000_000,
      soldCount: 0,
      totalRaised: 0,
      checkoutEnabled: true,
    });
    const checkout = await wrapCheckout();
    const form = checkoutForms.get(checkout.sessionId)!;
    expect(form.get("mode")).toBe("payment");
    expect(form.get("payment_method_types[0]")).toBe("card");
    expect(form.get("payment_intent_data[capture_method]")).toBe("automatic");
    expect(form.get("line_items[0][price_data][unit_amount]")).toBe("1000000");
    expect(form.get("line_items[0][price_data][product_data][name]")).toContain(
      "2 videos",
    );
    expect(form.get("custom_fields[0][key]")).toBe("brand");
    expect(form.get("success_url")).toContain("wrap=success");
    expect(form.get("metadata[custom_wrap_order_id]")).toBe(
      form.get("client_reference_id"),
    );
    expect(
      form.get("payment_intent_data[metadata][custom_wrap_order_id]"),
    ).toBe(form.get("client_reference_id"));
    expect(
      (await (
        await request("/api/custom-wrap/checkout", checkout.input)
      ).json()) as object,
    ).toMatchObject({ sessionId: checkout.sessionId });
    expect(
      (
        await request("/api/custom-wrap/checkout", {
          ...checkout.input,
          amount: 1_000_100,
        })
      ).status,
    ).toBe(409);
    expect(
      (await (
        await request("/api/custom-wrap/confirm", {
          sessionId: checkout.sessionId,
        })
      ).json()) as object,
    ).toMatchObject({ status: "pending", orderNumber: null });
    expect((await snapshot()).customWrap.soldCount).toBe(0);
    expect(wrapEmails()).toHaveLength(0);
    expect(wrapBuyerEmails()).toHaveLength(0);
  });
  it("rejects forged prices, missing acceptance, wrong origin and malformed confirmations", async () => {
    const input = {
      requestId: crypto.randomUUID(),
      amount: 1_000_001,
      acceptedTerms: true,
    };
    expect((await request("/api/custom-wrap/checkout", input)).status).toBe(
      409,
    );
    expect(
      (
        await request("/api/custom-wrap/checkout", {
          ...input,
          amount: 1_000_000,
          acceptedTerms: false,
        })
      ).status,
    ).toBe(400);
    expect(
      (
        await request("/api/custom-wrap/checkout", input, {
          Origin: "https://evil.example",
        })
      ).status,
    ).toBe(403);
    expect(
      (
        await request("/api/custom-wrap/confirm", {
          sessionId: "not-a-session",
        })
      ).status,
    ).toBe(400);
    expect(
      (
        await request("/api/custom-wrap/confirm", {
          sessionId: "cs_test_unknown",
        })
      ).status,
    ).toBe(404);
  });
  it("confirms once, opens $10,001 and emails the operator and buyer without changing sponsors", async () => {
    const before = await snapshot();
    const checkout = await wrapCheckout();
    const results = await Promise.all([
      pay(checkout.sessionId),
      pay(checkout.sessionId),
      pay(checkout.sessionId),
    ]);
    expect(results.every((result) => result.status === 200)).toBe(true);
    await expect.poll(() => wrapEmails().length).toBe(1);
    const after = await snapshot();
    expect(after.customWrap).toMatchObject({
      amount: 1_000_100,
      soldCount: 1,
      totalRaised: 1_000_000,
    });
    expect(after.totalRaised).toBe(before.totalRaised + 1_000_000);
    expect(after.revision).toBe(before.revision + 1);
    expect(after.placements).toEqual(before.placements);
    expect(after.history).toEqual(before.history);
    const mail = wrapEmails()[0];
    expect(mail.to).toBe("operator@example.test");
    expect(mail.subject).toContain("$10,000 custom wrap purchased");
    expect(mail.text).toContain("2 released project videos");
    expect(mail.text).toContain(`${checkout.sessionId}@example.test`);
    expect(mail.text).toContain("Wrap test studio");
    expect(mail.text).toContain(
      `https://dashboard.stripe.com/payments/pi_${checkout.sessionId}`,
    );
    expect(mail.text).toContain("You can start working");
    expect(wrapBuyerEmails()).toHaveLength(1);
    const welcome = wrapBuyerEmails()[0];
    expect(welcome.to).toBe(`${checkout.sessionId}@example.test`);
    expect(welcome.replyTo).toBe("operator@example.test");
    expect(welcome.subject).toContain("Your custom wrap is booked");
    expect(welcome.subject).not.toContain("[TEST]");
    expect(welcome.text).toContain("$10,000 USD");
    expect(welcome.text).toContain("2 released project videos");
    expect(welcome.text).toContain("Book a meeting with me ASAP");
    expect(welcome.text).toContain(
      "feel free to vibe, sketch, or start designing your wrap",
    );
    expect(welcome.text).toContain(WRAP_BOOKING_URL);
    expect(welcome.text).not.toContain(`${WRAP_BOOKING_URL},`);
    expect(welcome.text).toContain(WRAP_TEXTURE_URL);
    expect(welcome.html).toContain(`href="${WRAP_BOOKING_URL}"`);
    expect(welcome.html).toContain(`href="${WRAP_TEXTURE_URL}"`);
    expect(welcome.text).not.toContain("dashboard.stripe.com");
    const confirmation = await (
      await request("/api/custom-wrap/confirm", {
        sessionId: checkout.sessionId,
      })
    ).json();
    expect(confirmation as object).toMatchObject({
      status: "paid",
      orderNumber: 1,
    });
    expect(JSON.stringify(confirmation)).not.toMatch(
      /buyer_email|session_id|payment_id|example.test/,
    );
    expect(JSON.stringify(after)).not.toContain(checkout.sessionId);
    await pay(checkout.sessionId);
    await testStub.testAlarm();
    expect(wrapEmails()).toHaveLength(1);
    expect(wrapBuyerEmails()).toHaveLength(1);
  });
  it("refunds a simultaneous purchase at an old price without another increase or email", async () => {
    const before = await snapshot();
    const a = await wrapCheckout();
    const b = await wrapCheckout();
    const refundCount = refundRequests.length;
    const mailCount = wrapEmails().length;
    await Promise.all([pay(a.sessionId), pay(b.sessionId)]);
    await testStub.testAlarm();
    const rows = await testStub.testSql(
      "SELECT status FROM wrap_orders WHERE session_id IN (?,?)",
      a.sessionId,
      b.sessionId,
    );
    expect(rows.map((row) => row.status).sort()).toEqual(["paid", "refunded"]);
    expect((await snapshot()).customWrap.soldCount).toBe(
      before.customWrap.soldCount + 1,
    );
    expect((await snapshot()).customWrap.amount).toBe(
      before.customWrap.amount + 100,
    );
    expect(refundRequests.length).toBe(refundCount + 1);
    expect(wrapEmails().length).toBe(mailCount + 1);
    expect(wrapBuyerEmails()).toHaveLength(1);
    await Promise.all([pay(a.sessionId), pay(b.sessionId)]);
    await testStub.testAlarm();
    expect(refundRequests.length).toBe(refundCount + 1);
    expect(wrapEmails().length).toBe(mailCount + 1);
    expect((await request("/api/custom-wrap/checkout", a.input)).status).toBe(
      409,
    );
  });
  it("rejects authoritative Stripe mismatches without accepting the order", async () => {
    const checkout = await wrapCheckout();
    const session = sessions.get(checkout.sessionId)!;
    const before = (await snapshot()).customWrap.soldCount;
    const invalid: [string, unknown][] = [
      ["amount_total", 10],
      ["currency", "eur"],
      ["mode", "subscription"],
      ["client_reference_id", "some-other-order"],
      ["livemode", false],
      ["payment_intent", null],
      ["id", "cs_test_anotherSession"],
    ];
    for (const [key, value] of invalid) {
      const original = session[key];
      session[key] = value;
      const response =
        key === "id"
          ? await request("/api/custom-wrap/confirm", {
              sessionId: checkout.sessionId,
            })
          : await pay(checkout.sessionId);
      expect(response.status).toBe(400);
      session[key] = original;
    }
    expect((await snapshot()).customWrap.soldCount).toBe(before);
    session.status = "open";
    session.payment_status = "unpaid";
  });
  it("recovers missed webhooks through the alarm and retries email after a restart", async () => {
    const checkout = await wrapCheckout();
    const mailCount = wrapEmails().length;
    const session = sessions.get(checkout.sessionId)!;
    session.status = "complete";
    session.payment_status = "paid";
    failEmail = true;
    try {
      expect(await testStub.testAlarm()).not.toBeNull();
      expect(wrapEmails().length).toBe(mailCount);
      const rows = await testStub.testSql(
        "SELECT o.status, n.status AS notification_status, n.attempts FROM wrap_orders o JOIN wrap_notifications n ON o.id = n.order_id WHERE o.session_id = ?",
        checkout.sessionId,
      );
      expect(rows[0]).toMatchObject({
        status: "paid",
        notification_status: "pending",
      });
      expect(rows).toHaveLength(2);
      expect(rows.every((row) => Number(row.attempts) > 0)).toBe(true);
      await mf.setOptions(mfOptions);
      const namespace = await mf.getDurableObjectNamespace("AUCTION");
      testStub = namespace.get(
        namespace.idFromName("the-driving-fly-v1"),
      ) as unknown as TestStub;
      await testStub.testSql(
        "UPDATE wrap_notifications SET next_attempt_at = 0 WHERE order_id = (SELECT id FROM wrap_orders WHERE session_id = ?)",
        checkout.sessionId,
      );
    } finally {
      failEmail = false;
    }
    await testStub.testAlarm();
    await expect.poll(() => wrapEmails().length).toBe(mailCount + 1);
    await testStub.testAlarm();
    expect(wrapEmails().length).toBe(mailCount + 1);
    expect(wrapBuyerEmails()).toHaveLength(1);
  });
  it.each(["buyer", "operator"])(
    "retries only the failed %s email after a restart",
    async (audience) => {
      const checkout = await wrapCheckout();
      failEmailAudience = audience;
      await pay(checkout.sessionId);
      await testStub.testAlarm();
      expect(wrapEmails()).toHaveLength(audience === "operator" ? 0 : 1);
      expect(wrapBuyerEmails()).toHaveLength(audience === "buyer" ? 0 : 1);
      const jobs = await testStub.testSql(
        "SELECT audience, status, attempts FROM wrap_notifications",
      );
      expect(jobs.find((job) => job.audience === audience)).toMatchObject({
        status: "pending",
      });
      expect(jobs.find((job) => job.audience !== audience)).toMatchObject({
        status: "sent",
      });
      await mf.setOptions(mfOptions);
      const namespace = await mf.getDurableObjectNamespace("AUCTION");
      testStub = namespace.get(
        namespace.idFromName("the-driving-fly-v1"),
      ) as unknown as TestStub;
      failEmailAudience = undefined;
      await testStub.testSql(
        "UPDATE wrap_notifications SET next_attempt_at = 0",
      );
      await testStub.testAlarm();
      expect(wrapEmails()).toHaveLength(1);
      expect(wrapBuyerEmails()).toHaveLength(1);
      await pay(checkout.sessionId);
      await testStub.testAlarm();
      expect(wrapEmails()).toHaveLength(1);
      expect(wrapBuyerEmails()).toHaveLength(1);
    },
  );
  it("recovers a paid checkout whose session ID and webhook were lost", async () => {
    const checkout = await wrapCheckout();
    const session = sessions.get(checkout.sessionId)!;
    session.status = "complete";
    session.payment_status = "paid";
    await testStub.testSql(
      "UPDATE wrap_orders SET session_id = NULL WHERE session_id = ?",
      checkout.sessionId,
    );
    const before = (await snapshot()).customWrap;
    await testStub.testAlarm();
    expect((await snapshot()).customWrap.soldCount).toBe(before.soldCount + 1);
    expect(wrapEmails()).toHaveLength(1);
    expect(wrapBuyerEmails()).toHaveLength(1);
    await testStub.testAlarm();
    expect(wrapEmails()).toHaveLength(1);
    expect(wrapBuyerEmails()).toHaveLength(1);
  });
  it("verifies payment when the buyer returns before a webhook", async () => {
    const checkout = await wrapCheckout();
    const session = sessions.get(checkout.sessionId)!;
    session.status = "complete";
    session.payment_status = "paid";
    const before = (await snapshot()).customWrap;
    expect(
      (await (
        await request("/api/custom-wrap/confirm", {
          sessionId: checkout.sessionId,
        })
      ).json()) as object,
    ).toMatchObject({ status: "paid", orderNumber: before.soldCount + 1 });
    expect((await snapshot()).customWrap.amount).toBe(before.amount + 100);
    await testStub.testAlarm();
  });
  it("does not describe pending or failed refunds as completed", async () => {
    const a = await wrapCheckout();
    const b = await wrapCheckout();
    await pay(a.sessionId);
    const session = sessions.get(b.sessionId)!;
    const refundId = `re_${session.payment_intent}`;
    refunds.set(refundId, { id: refundId, status: "pending" });
    await testStub.testSql(
      "UPDATE wrap_orders SET refund_id = ? WHERE session_id = ?",
      refundId,
      b.sessionId,
    );
    await pay(b.sessionId);
    await testStub.testAlarm();
    const status = async () =>
      (
        await testStub.testSql(
          "SELECT status FROM wrap_orders WHERE session_id = ?",
          b.sessionId,
        )
      )[0].status;
    expect(await status()).toBe("refund_pending");
    refunds.set(refundId, { id: refundId, status: "failed" });
    await testStub.testAlarm();
    expect(await status()).toBe("refund_pending");
    refunds.set(refundId, { id: refundId, status: "succeeded" });
    await testStub.testAlarm();
    expect(await status()).toBe("refunded");
  });
  it("requires notification configuration and isolates sandbox alerts", async () => {
    await testStub.testWrapConfig();
    expect((await snapshot()).customWrap.checkoutEnabled).toBe(false);
    expect(
      (
        await request("/api/custom-wrap/checkout", {
          requestId: crypto.randomUUID(),
          amount: (await snapshot()).customWrap.amount,
          acceptedTerms: true,
        })
      ).status,
    ).toBe(503);
    testMode = true;
    await testStub.testConfig(true);
    await testStub.testWrapConfig("operator@example.test");
    expect((await snapshot()).customWrap.checkoutEnabled).toBe(false);
    await testStub.testWrapConfig(
      "operator@example.test",
      "wrap-sandbox@example.test",
    );
    try {
      const checkout = await wrapCheckout();
      await pay(checkout.sessionId);
      await testStub.testAlarm();
      const mail = wrapEmails().at(-1)!;
      expect(mail.to).toBe("wrap-sandbox@example.test");
      expect(mail.subject).toContain("[TEST]");
      expect(mail.text).toContain("Do not begin production");
      expect(mail.text).toContain("stripe.com/test/payments/");
      const buyerMail = wrapBuyerEmails().at(-1)!;
      expect(buyerMail.to).toBe("wrap-sandbox@example.test");
      expect(buyerMail.replyTo).toBe("wrap-sandbox@example.test");
      expect(buyerMail.subject).toContain("[TEST]");
      expect(buyerMail.text).toContain(
        "Do not book a meeting or begin production",
      );
      expect(buyerMail.text).toContain(WRAP_BOOKING_URL);
      expect(buyerMail.text).toContain(WRAP_TEXTURE_URL);
      expect(buyerMail.to).not.toBe(`${checkout.sessionId}@example.test`);
    } finally {
      testMode = false;
      await testStub.testConfig(false);
      await testStub.testWrapConfig("operator@example.test");
    }
  });
});
