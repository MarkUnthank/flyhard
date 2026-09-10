import { afterAll, beforeAll, describe, expect, it } from "vitest";
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
const refunds = new Map<string, Record<string, unknown>>();
const refundRequests: string[] = [];
const emails: EmailMessageBuilder[] = [];
let failEmail = false;
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
      if (failEmail)
        return new WorkerResponse("Temporary failure", { status: 503 });
      emails.push((await request.json()) as EmailMessageBuilder);
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
          livemode: !testMode,
          customer_details: { email: `${id}@example.test` },
          payment_intent: `pi_${id}`,
          url: `https://checkout.stripe.com/c/pay/${id}`,
        });
      }
      return WorkerResponse.json(sessions.get(id));
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
      STRIPE_API_KEY: "local_live_fixture",
      OUTBID_EMAIL_FROM: "updates@notify.example.test",
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
    expect(counts).toEqual({ left: 2, right: 1, top: 2, front: 1, back: 1 });
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
      width_m: 1.16,
      height_m: 0.95,
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
});
