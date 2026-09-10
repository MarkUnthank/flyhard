import { DurableObject } from "cloudflare:workers";
import Stripe from "stripe";
import { decode, encode } from "fast-png";
import {
  bidSchema,
  minimumBid,
  money,
  slots,
  activeSlots,
  type AuctionSnapshot,
  type Placement,
} from "../src/lib/auction";
import { checkoutEmail, emailErrorCode, outbidEmail } from "./outbid-email";
import type { Env } from "./env";
import { HttpError, json, readBody, readJson } from "./http";

type BidRow = {
  id: string;
  request_id: string;
  slot_id: string;
  amount: number;
  brand: string;
  message: string;
  url: string;
  artwork_token: string;
  logo_token: string;
  status: string;
  session_id: string | null;
  payment_id: string | null;
  buyer_email: string | null;
  refund_id: string | null;
  created_at: number;
  published_at: number | null;
};
type UploadRow = { token: string; created_at: number; bid_id: string | null };
const DAY = 86_400_000;

export class Auction extends DurableObject<Env> {
  private sql: SqlStorage;
  private notificationWork: Promise<void> | undefined;
  private refundWork: Promise<void> | undefined;
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS bids (
        id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, slot_id TEXT NOT NULL,
        amount INTEGER NOT NULL, brand TEXT NOT NULL, url TEXT NOT NULL,
        message TEXT NOT NULL DEFAULT '', logo_token TEXT NOT NULL,
        artwork_token TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        session_id TEXT UNIQUE, payment_id TEXT UNIQUE, refund_id TEXT, created_at INTEGER NOT NULL,
        published_at INTEGER, checked_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS placements (slot_id TEXT PRIMARY KEY, bid_id TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS uploads (token TEXT PRIMARY KEY, created_at INTEGER NOT NULL, bid_id TEXT);
      CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
      INSERT OR IGNORE INTO counters VALUES ('revision', 0);
      CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS outbid_emails (
        previous_bid_id TEXT PRIMARY KEY, replacement_bid_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
        sent_at INTEGER, message_id TEXT, last_error TEXT
      );
      CREATE INDEX IF NOT EXISTS email_pending ON outbid_emails(status, next_attempt_at);
      CREATE INDEX IF NOT EXISTS bid_status ON bids(status);
      CREATE INDEX IF NOT EXISTS bid_publication ON bids(published_at);
    `);
    // Migrate stored purchases before serving the new advertiser profiles.
    const columns = new Set(
      this.sql
        .exec<{ name: string }>("PRAGMA table_info(bids)")
        .toArray()
        .map((column) => column.name),
    );
    this.ctx.storage.transactionSync(() => {
      if (!columns.has("buyer_email"))
        this.sql.exec("ALTER TABLE bids ADD COLUMN buyer_email TEXT");
      if (!columns.has("message"))
        this.sql.exec(
          "ALTER TABLE bids ADD COLUMN message TEXT NOT NULL DEFAULT ''",
        );
      if (!columns.has("logo_token")) {
        this.sql.exec(
          "ALTER TABLE bids ADD COLUMN logo_token TEXT NOT NULL DEFAULT ''",
        );
        this.sql.exec("UPDATE bids SET logo_token = artwork_token");
      }
    });
    // Recover queued notifications after a deployment or sender configuration change.
    if (
      this.canSendOutbidEmails() &&
      this.sql
        .exec<{ count: number }>(
          "SELECT COUNT(*) AS count FROM outbid_emails WHERE status = 'pending'",
        )
        .one().count
    )
      this.ctx.blockConcurrencyWhile(() => this.scheduleAlarm());
  }

  private stripe() {
    if (!this.env.STRIPE_API_KEY)
      throw new HttpError(
        503,
        "Checkout is not connected yet. Please try again later.",
      );
    return new Stripe(this.env.STRIPE_API_KEY, {
      httpClient: Stripe.createFetchHttpClient(),
      maxNetworkRetries: 2,
    });
  }
  private placement(row: BidRow): Placement {
    return {
      id: row.id,
      slotId: row.slot_id,
      brand: row.brand,
      message: row.message,
      url: row.url,
      amount: row.amount,
      textureUrl: `/api/artwork/${row.artwork_token}.png`,
      logoUrl: `/api/artwork/${row.logo_token}.png`,
      publishedAt: row.published_at!,
    };
  }
  private snapshot(): AuctionSnapshot {
    const current = this.sql
      .exec<BidRow>(
        "SELECT b.* FROM placements p JOIN bids b ON b.id = p.bid_id",
      )
      .toArray();
    const history = this.sql
      .exec<BidRow>(
        "SELECT * FROM bids WHERE published_at IS NOT NULL ORDER BY published_at DESC, rowid DESC LIMIT 50",
      )
      .toArray();
    const totals = this.sql
      .exec<{ total: number; count: number }>(
        "SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM bids WHERE published_at IS NOT NULL",
      )
      .one();
    return {
      activeSlotIds: activeSlots(
        Object.fromEntries(
          current.map((row) => [row.slot_id, this.placement(row)]),
        ),
      ).map((slot) => slot.id),
      revision: this.sql
        .exec<{ value: number }>(
          "SELECT value FROM counters WHERE name = 'revision'",
        )
        .one().value,
      placements: Object.fromEntries(
        current.map((row) => [row.slot_id, this.placement(row)]),
      ),
      history: history.map((row) => this.placement(row)),
      totalRaised: totals.total,
      totalPurchases: totals.count,
      online: this.ctx.getWebSockets().length,
      paymentsEnabled: Boolean(
        this.env.STRIPE_API_KEY && this.env.STRIPE_WEBHOOK_SECRET,
      ),
      paymentMode: this.env.STRIPE_API_KEY?.includes("_test_")
        ? "test"
        : this.env.STRIPE_API_KEY
          ? "live"
          : "unavailable",
    };
  }
  private broadcast() {
    const message = JSON.stringify(this.snapshot());
    for (const socket of this.ctx.getWebSockets()) {
      try {
        socket.send(message);
      } catch {
        socket.close(1011, "Reconnect");
      }
    }
  }
  private checkOrigin(request: Request) {
    if (request.headers.get("Origin") !== this.env.SITE_URL)
      throw new HttpError(403, "Open checkout from The Driving Fly website.");
  }
  private rateLimit(request: Request, action: string, maximum = 12) {
    const now = Date.now();
    const key = `${action}:${request.headers.get("CF-Connecting-IP") || "local"}:${Math.floor(now / 60_000)}`;
    this.sql.exec(
      "INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count = count + 1",
      key,
      now + 120_000,
    );
    if (
      this.sql
        .exec<{ count: number }>("SELECT count FROM limits WHERE key = ?", key)
        .one().count > maximum
    )
      throw new HttpError(429, "Please wait a minute before trying again.");
    this.sql.exec("DELETE FROM limits WHERE expires_at < ?", now);
  }
  private async scheduleAlarm() {
    const next = Date.now() + 60_000;
    const current = await this.ctx.storage.getAlarm();
    if (!current || current > next) await this.ctx.storage.setAlarm(next);
  }

  async fetch(request: Request): Promise<Response> {
    try {
      const url = new URL(request.url);
      const path = url.pathname;
      if (request.method === "GET" && path === "/api/live") {
        this.checkOrigin(request);
        if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket")
          throw new HttpError(426, "WebSocket upgrade required.");
        if (this.ctx.getWebSockets().length >= 1000)
          throw new HttpError(
            503,
            "Live updates are busy; reconnecting shortly.",
          );
        const pair = new WebSocketPair();
        this.ctx.acceptWebSocket(pair[1]);
        this.ctx.setWebSocketAutoResponse(
          new WebSocketRequestResponsePair("ping", "pong"),
        );
        this.broadcast();
        return new Response(null, { status: 101, webSocket: pair[0] });
      }
      if (
        request.method === "GET" &&
        (path === "/api/auction" || path === "/api/livery")
      )
        return json(this.snapshot());
      if (request.method === "GET" && path.startsWith("/api/artwork/"))
        return await this.artwork(path);
      if (request.method === "POST" && path === "/api/stripe/webhook")
        return await this.webhook(request);
      if (request.method === "POST") {
        this.checkOrigin(request);
        this.rateLimit(request, path, path.endsWith("confirm") ? 60 : 12);
        if (path === "/api/artwork") return await this.upload(request);
        if (path === "/api/checkout") return await this.checkout(request);
        if (path === "/api/checkout/confirm")
          return await this.confirm(request);
      }
      throw new HttpError(404, "Not found.");
    } catch (error) {
      if (error instanceof HttpError)
        return json({ error: error.message }, error.status);
      console.error(
        "Auction request failed",
        error instanceof Error ? error.name : "Unknown error",
      );
      return json(
        { error: "We couldn’t complete that request. Please try again." },
        500,
      );
    }
  }

  private async upload(request: Request) {
    const bytes = await readBody(request, 1_500_000);
    // Only bounded PNGs are accepted. Decode + encode strips metadata and rejects
    // malformed files, so uploaded content never becomes executable SVG/HTML.
    if (
      bytes.length < 33 ||
      ![137, 80, 78, 71, 13, 10, 26, 10].every((n, i) => bytes[i] === n)
    )
      throw new HttpError(400, "Upload a PNG image.");
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const width = view.getUint32(16),
      height = view.getUint32(20);
    if (!width || !height || width > 1024 || height > 1024 || bytes[24] !== 8)
      throw new HttpError(400, "Use an 8-bit PNG, at most 1024 × 1024 pixels.");
    let png: Uint8Array;
    try {
      png = encode(decode(bytes, { checkCrc: true }));
    } catch {
      throw new HttpError(
        400,
        "This image could not be read. Please choose another.",
      );
    }
    const token = crypto.randomUUID();
    await this.env.ARTWORK.put(`${token}.png`, png, {
      httpMetadata: { contentType: "image/png" },
    });
    this.sql.exec("INSERT INTO uploads VALUES (?,?,NULL)", token, Date.now());
    await this.scheduleAlarm();
    return json({ token }, 201);
  }
  private async artwork(path: string) {
    const match = /^\/api\/artwork\/([a-f0-9-]{36})\.png$/.exec(path);
    if (!match) throw new HttpError(404, "Artwork not found.");
    const published = this.sql
      .exec(
        "SELECT id FROM bids WHERE (artwork_token = ? OR logo_token = ?) AND published_at IS NOT NULL LIMIT 1",
        match[1],
        match[1],
      )
      .toArray();
    if (!published.length) throw new HttpError(404, "Artwork not found.");
    const object = await this.env.ARTWORK.get(`${match[1]}.png`);
    if (!object) throw new HttpError(404, "Artwork not found.");
    return new Response(object.body, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=31536000, immutable",
        ETag: object.httpEtag,
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
      },
    });
  }

  private async checkout(request: Request) {
    if (!this.env.STRIPE_WEBHOOK_SECRET)
      throw new HttpError(
        503,
        "Checkout is not connected yet. Please try again later.",
      );
    const parsed = bidSchema.safeParse(await readJson(request));
    if (!parsed.success)
      throw new HttpError(400, parsed.error.issues[0].message);
    const input = parsed.data;
    let bid = this.sql
      .exec<BidRow>("SELECT * FROM bids WHERE request_id = ?", input.requestId)
      .toArray()[0];
    if (bid) {
      if (
        bid.slot_id !== input.slotId ||
        bid.amount !== input.amount ||
        bid.brand !== input.brand ||
        bid.message !== input.message ||
        bid.url !== input.url ||
        bid.artwork_token !== input.artworkToken ||
        bid.logo_token !== input.logoToken
      )
        throw new HttpError(
          409,
          "This checkout changed. Start a new checkout.",
        );
      if (bid.status !== "pending" || bid.created_at < Date.now() - 31 * 60_000)
        throw new HttpError(
          409,
          "This checkout has ended. Start a new checkout.",
        );
    } else {
      const snapshot = this.snapshot();
      if (!snapshot.activeSlotIds.includes(input.slotId))
        throw new HttpError(
          409,
          `This spot has been retired. Choose one of the ${snapshot.activeSlotIds.length} current spots.`,
        );
      const current = snapshot.placements[input.slotId];
      if (input.amount < minimumBid(current?.amount))
        throw new HttpError(
          409,
          `This spot changed. The new minimum is ${money(minimumBid(current?.amount))}.`,
        );
      const tokens = new Set([input.artworkToken, input.logoToken]);
      for (const token of tokens) {
        const upload = this.sql
          .exec<UploadRow>("SELECT * FROM uploads WHERE token = ?", token)
          .toArray()[0];
        if (!upload || upload.bid_id || upload.created_at < Date.now() - DAY)
          throw new HttpError(400, "Please upload your artwork again.");
      }
      const id = crypto.randomUUID();
      this.ctx.storage.transactionSync(() => {
        this.sql.exec(
          "INSERT INTO bids (id,request_id,slot_id,amount,brand,message,url,artwork_token,logo_token,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
          id,
          input.requestId,
          input.slotId,
          input.amount,
          input.brand,
          input.message,
          input.url,
          input.artworkToken,
          input.logoToken,
          Date.now(),
        );
        for (const token of tokens)
          this.sql.exec(
            "UPDATE uploads SET bid_id = ? WHERE token = ?",
            id,
            token,
          );
      });
      bid = this.sql.exec<BidRow>("SELECT * FROM bids WHERE id = ?", id).one();
    }
    await this.scheduleAlarm();
    const stripe = this.stripe();
    const session = bid.session_id
      ? await stripe.checkout.sessions.retrieve(bid.session_id)
      : await stripe.checkout.sessions.create(
          {
            mode: "payment",
            payment_method_types: ["card"],
            line_items: [
              {
                quantity: 1,
                price_data: {
                  currency: "usd",
                  unit_amount: bid.amount,
                  product_data: {
                    name: `The Driving Fly · ${slots.find((s) => s.id === bid.slot_id)!.name}`,
                    description:
                      "Your artwork goes live after payment and stays until someone pays at least $1 more. No fixed display time. A later outbid is not refunded.",
                  },
                },
              },
            ],
            client_reference_id: bid.id,
            metadata: { bid_id: bid.id },
            payment_intent_data: { metadata: { bid_id: bid.id } },
            success_url: `${this.env.SITE_URL}/?checkout=success&session_id={CHECKOUT_SESSION_ID}#live-auction`,
            cancel_url: `${this.env.SITE_URL}/?checkout=cancelled#live-auction`,
            expires_at: Math.floor(bid.created_at / 1000) + 31 * 60,
            custom_text: {
              submit: {
                message:
                  "One-time payment. Your placement lasts until someone pays at least $1 more. If this payment is already beaten before publication, it is automatically refunded.",
              },
            },
          },
          { idempotencyKey: `checkout:${bid.id}` },
        );
    this.sql.exec(
      "UPDATE bids SET session_id = ? WHERE id = ?",
      session.id,
      bid.id,
    );
    await this.scheduleAlarm();
    if (session.status !== "open" || !session.url)
      throw new HttpError(
        409,
        "This checkout has ended. Start a new checkout.",
      );
    return json({ url: session.url, sessionId: session.id });
  }

  private async confirm(request: Request) {
    const input = await readJson(request);
    if (
      typeof input.sessionId !== "string" ||
      !/^cs_(test_|live_)?[A-Za-z0-9]+$/.test(input.sessionId) ||
      input.sessionId.length > 250
    )
      throw new HttpError(400, "Invalid checkout session.");
    const bid = this.sql
      .exec<BidRow>("SELECT * FROM bids WHERE session_id = ?", input.sessionId)
      .toArray()[0];
    if (!bid) throw new HttpError(404, "Checkout not found.");
    if (bid.status === "pending")
      await this.fulfill(
        await this.stripe().checkout.sessions.retrieve(input.sessionId),
      );
    const updated = this.sql
      .exec<BidRow>("SELECT * FROM bids WHERE id = ?", bid.id)
      .one();
    return json({
      status: updated.status,
      slotId: updated.slot_id,
      snapshot: this.snapshot(),
    });
  }
  private async webhook(request: Request) {
    if (!this.env.STRIPE_WEBHOOK_SECRET)
      throw new HttpError(503, "Webhook is not configured.");
    const signature = request.headers.get("Stripe-Signature");
    if (!signature) throw new HttpError(400, "Missing webhook signature.");
    let event: Stripe.Event;
    const body = new TextDecoder().decode(await readBody(request, 1_000_000));
    try {
      event = await this.stripe().webhooks.constructEventAsync(
        body,
        signature,
        this.env.STRIPE_WEBHOOK_SECRET,
        undefined,
        Stripe.createSubtleCryptoProvider(),
      );
    } catch {
      throw new HttpError(400, "Invalid webhook signature.");
    }
    if (
      event.type === "checkout.session.completed" ||
      event.type === "checkout.session.async_payment_succeeded"
    ) {
      // Re-read authoritative Stripe state. Never trust browser amounts or return URLs.
      await this.fulfill(
        await this.stripe().checkout.sessions.retrieve(event.data.object.id),
      );
    }
    return json({ received: true });
  }

  private async fulfill(session: Stripe.Checkout.Session) {
    if (session.payment_status !== "paid" || session.status !== "complete")
      return;
    const bidId = session.metadata?.bid_id;
    const bid = this.sql
      .exec<BidRow>("SELECT * FROM bids WHERE id = ?", bidId || "")
      .toArray()[0];
    if (!bid) return; // Other Stripe products may share this account.
    if (
      session.mode !== "payment" ||
      session.currency !== "usd" ||
      session.amount_total !== bid.amount ||
      session.client_reference_id !== bid.id ||
      (bid.session_id && session.id !== bid.session_id) ||
      !session.payment_intent ||
      session.livemode !== !this.env.STRIPE_API_KEY?.includes("_test_")
    )
      throw new HttpError(400, "Payment does not match this bid.");
    const paymentId =
      typeof session.payment_intent === "string"
        ? session.payment_intent
        : session.payment_intent.id;
    // Establish a durable recovery alarm before the transaction creates refund work.
    await this.scheduleAlarm();
    let changed = false;
    this.ctx.storage.transactionSync(() => {
      const latest = this.sql
        .exec<BidRow>("SELECT * FROM bids WHERE id = ?", bid.id)
        .one();
      if (latest.status !== "pending") return;
      const current = this.sql
        .exec<BidRow>(
          "SELECT b.* FROM placements p JOIN bids b ON b.id = p.bid_id WHERE p.slot_id = ?",
          bid.slot_id,
        )
        .toArray()[0];
      this.sql.exec(
        "UPDATE bids SET session_id = ?, payment_id = ?, buyer_email = ? WHERE id = ?",
        session.id,
        paymentId,
        checkoutEmail(session),
        bid.id,
      );
      if (bid.amount < minimumBid(current?.amount)) {
        this.sql.exec(
          "UPDATE bids SET status = 'refund_pending' WHERE id = ?",
          bid.id,
        );
        return;
      }
      if (current) {
        this.sql.exec(
          "UPDATE bids SET status = 'outbid' WHERE id = ?",
          current.id,
        );
        // The notification and ownership change commit together. Never enqueue
        // for a checkout that loses before its artwork has been published.
        this.sql.exec(
          "INSERT OR IGNORE INTO outbid_emails (previous_bid_id, replacement_bid_id, created_at) VALUES (?,?,?)",
          current.id,
          bid.id,
          Date.now(),
        );
      }
      this.sql.exec(
        "UPDATE bids SET status = 'won', published_at = ? WHERE id = ?",
        Date.now(),
        bid.id,
      );
      this.sql.exec(
        "INSERT INTO placements VALUES (?,?) ON CONFLICT(slot_id) DO UPDATE SET bid_id = excluded.bid_id",
        bid.slot_id,
        bid.id,
      );
      this.sql.exec(
        "UPDATE counters SET value = value + 1 WHERE name = 'revision'",
      );
      changed = true;
    });
    if (changed) {
      this.broadcast();
      // Durable alarm recovery is already armed; email cannot delay publication.
      this.ctx.waitUntil(this.notifyOutbid());
    }
    await this.refundPending();
  }
  private async bidderEmail(bid: BidRow): Promise<string | null> {
    if (bid.buyer_email) return bid.buyer_email;
    if (!bid.session_id) return null;
    // Existing sponsors predate email storage. Retrieve only the displaced
    // owner's original paid Checkout, never take an address from the browser.
    const session = await this.stripe().checkout.sessions.retrieve(
      bid.session_id,
    );
    if (
      session.client_reference_id !== bid.id ||
      session.metadata?.bid_id !== bid.id ||
      session.payment_status !== "paid" ||
      session.status !== "complete" ||
      session.amount_total !== bid.amount ||
      session.currency !== "usd" ||
      session.livemode !== !this.env.STRIPE_API_KEY?.includes("_test_")
    )
      throw new Error("Stored checkout identity mismatch");
    const email = checkoutEmail(session);
    if (email)
      this.sql.exec(
        "UPDATE bids SET buyer_email = ? WHERE id = ?",
        email,
        bid.id,
      );
    return email;
  }

  private async notifyOutbid() {
    const work = (this.notificationWork ?? Promise.resolve())
      .catch(() => {})
      .then(() => this.processOutbidEmails());
    this.notificationWork = work;
    try {
      await work;
    } finally {
      if (this.notificationWork === work) this.notificationWork = undefined;
    }
  }

  private canSendOutbidEmails() {
    return Boolean(
      this.env.EMAIL &&
      this.env.OUTBID_EMAIL_FROM &&
      this.env.STRIPE_API_KEY &&
      (!this.env.STRIPE_API_KEY.includes("_test_") ||
        this.env.OUTBID_EMAIL_TEST_TO),
    );
  }

  private async processOutbidEmails() {
    // Local development has no email binding. Staging fails closed unless an
    // explicit test recipient is configured; it never emails real sponsors.
    if (!this.canSendOutbidEmails()) return;
    const test = Boolean(this.env.STRIPE_API_KEY?.includes("_test_"));
    const jobs = this.sql
      .exec<{
        previous_bid_id: string;
        replacement_bid_id: string;
        attempts: number;
      }>(
        "SELECT * FROM outbid_emails WHERE status = 'pending' AND next_attempt_at <= ? ORDER BY created_at LIMIT 20",
        Date.now(),
      )
      .toArray();
    for (const job of jobs) {
      try {
        const previous = this.sql
          .exec<BidRow>("SELECT * FROM bids WHERE id = ?", job.previous_bid_id)
          .one();
        const replacement = this.sql
          .exec<BidRow>(
            "SELECT * FROM bids WHERE id = ?",
            job.replacement_bid_id,
          )
          .one();
        const recipient = await this.bidderEmail(previous);
        if (!recipient) {
          this.finishNotification(
            job.previous_bid_id,
            "failed",
            "E_NO_CHECKOUT_EMAIL",
          );
          continue;
        }
        const replacementEmail = await this.bidderEmail(replacement);
        const current = this.sql
          .exec<BidRow>(
            "SELECT b.* FROM placements p JOIN bids b ON b.id = p.bid_id WHERE p.slot_id = ?",
            previous.slot_id,
          )
          .one();
        if (
          replacementEmail?.toLowerCase() === recipient.toLowerCase() ||
          current.buyer_email?.toLowerCase() === recipient.toLowerCase()
        ) {
          this.finishNotification(
            job.previous_bid_id,
            "skipped",
            "E_OWNER_RETAINED_SPOT",
          );
          continue;
        }
        this.sql.exec(
          "UPDATE outbid_emails SET attempts = attempts + 1 WHERE previous_bid_id = ?",
          job.previous_bid_id,
        );
        const result = await this.env.EMAIL!.send({
          from: { name: "The Driving Fly", email: this.env.OUTBID_EMAIL_FROM! },
          to: test ? this.env.OUTBID_EMAIL_TEST_TO! : recipient,
          headers: {
            "X-Outbid-Notification": job.previous_bid_id,
            "Auto-Submitted": "auto-generated",
          },
          ...outbidEmail({
            siteUrl: this.env.SITE_URL,
            slotId: previous.slot_id,
            slotName:
              slots.find((slot) => slot.id === previous.slot_id)?.name ??
              previous.slot_id,
            brand: previous.brand,
            previousAmount: previous.amount,
            replacementAmount: replacement.amount,
            currentAmount: current.amount,
            test,
          }),
        });
        this.sql.exec(
          "UPDATE outbid_emails SET status = 'sent', sent_at = ?, message_id = ?, last_error = NULL WHERE previous_bid_id = ?",
          Date.now(),
          result.messageId,
          job.previous_bid_id,
        );
        console.info(
          "Outbid email accepted",
          job.previous_bid_id,
          result.messageId,
        );
      } catch (error) {
        const code = emailErrorCode(error);
        if (code === "E_RECIPIENT_SUPPRESSED") {
          this.finishNotification(job.previous_bid_id, "failed", code);
        } else {
          const delay = Math.min(
            3_600_000,
            60_000 * 2 ** Math.min(job.attempts, 6),
          );
          this.sql.exec(
            "UPDATE outbid_emails SET attempts = ?, next_attempt_at = ?, last_error = ? WHERE previous_bid_id = ?",
            job.attempts + 1,
            Date.now() + delay,
            code,
            job.previous_bid_id,
          );
          console.error("Outbid email will retry", job.previous_bid_id, code);
        }
      }
    }
  }

  private finishNotification(id: string, status: string, code: string) {
    this.sql.exec(
      "UPDATE outbid_emails SET status = ?, last_error = ? WHERE previous_bid_id = ?",
      status,
      code,
      id,
    );
    if (status === "failed")
      console.error("Outbid email needs attention", id, code);
  }

  private async refundPending() {
    // Webhooks can interleave while a Stripe request is in flight. Serialize
    // refund scans within this instance; Stripe idempotency covers restarts.
    const work = (this.refundWork ?? Promise.resolve())
      .catch(() => {})
      .then(() => this.processRefunds());
    this.refundWork = work;
    try {
      await work;
    } finally {
      if (this.refundWork === work) this.refundWork = undefined;
    }
  }

  private async processRefunds() {
    for (const bid of this.sql
      .exec<BidRow>(
        "SELECT * FROM bids WHERE status = 'refund_pending' LIMIT 20",
      )
      .toArray()) {
      try {
        const refund = bid.refund_id
          ? await this.stripe().refunds.retrieve(bid.refund_id)
          : await this.stripe().refunds.create(
              {
                payment_intent: bid.payment_id!,
                metadata: {
                  bid_id: bid.id,
                  reason: "Outbid before publication",
                },
              },
              { idempotencyKey: `refund:${bid.id}` },
            );
        this.sql.exec(
          "UPDATE bids SET refund_id = ? WHERE id = ?",
          refund.id,
          bid.id,
        );
        if (refund.status === "succeeded")
          this.sql.exec(
            "UPDATE bids SET status = 'refunded' WHERE id = ? AND status = 'refund_pending'",
            bid.id,
          );
        // Pending and failed refunds remain visible and are retried by the alarm.
      } catch {
        console.error("Refund will retry", bid.id);
      }
    }
  }
  async alarm() {
    // Re-arm first: a failed remote call must not strand a paid checkout or refund.
    await this.ctx.storage.setAlarm(Date.now() + 60_000);
    await this.refundPending();
    await this.notifyOutbid();
    const pending = this.sql
      .exec<BidRow>(
        "SELECT * FROM bids WHERE status = 'pending' AND session_id IS NOT NULL AND created_at < ? ORDER BY checked_at LIMIT 20",
        Date.now() - 60_000,
      )
      .toArray();
    for (const bid of pending) {
      try {
        const session = await this.stripe().checkout.sessions.retrieve(
          bid.session_id!,
        );
        await this.fulfill(session);
        if (session.status === "expired")
          this.sql.exec(
            "UPDATE bids SET status = 'expired' WHERE id = ? AND status = 'pending'",
            bid.id,
          );
      } catch {
        console.error("Checkout reconciliation will retry", bid.id);
      }
      this.sql.exec(
        "UPDATE bids SET checked_at = ? WHERE id = ?",
        Date.now(),
        bid.id,
      );
    }
    this.sql.exec(
      "UPDATE bids SET status = 'expired' WHERE status = 'pending' AND session_id IS NULL AND created_at < ?",
      Date.now() - DAY,
    );
    const abandoned = this.sql
      .exec<UploadRow>(
        "SELECT u.* FROM uploads u LEFT JOIN bids b ON b.id = u.bid_id WHERE u.created_at < ? AND (u.bid_id IS NULL OR b.status = 'expired') LIMIT 100",
        Date.now() - DAY,
      )
      .toArray();
    for (const upload of abandoned) {
      await this.env.ARTWORK.delete(`${upload.token}.png`);
      this.sql.exec("DELETE FROM uploads WHERE token = ?", upload.token);
    }
    this.sql.exec("DELETE FROM limits WHERE expires_at < ?", Date.now());
    const work = this.sql
      .exec<{ count: number }>(
        "SELECT COUNT(*) AS count FROM uploads u LEFT JOIN bids b ON b.id = u.bid_id WHERE u.bid_id IS NULL OR b.status IN ('pending','refund_pending','expired')",
      )
      .one().count;
    if (!work) {
      const nextEmail = this.canSendOutbidEmails()
        ? this.sql
            .exec<{ due: number | null }>(
              "SELECT MIN(next_attempt_at) AS due FROM outbid_emails WHERE status = 'pending'",
            )
            .one().due
        : null;
      if (nextEmail === null) await this.ctx.storage.deleteAlarm();
      else
        await this.ctx.storage.setAlarm(
          Math.max(Date.now() + 60_000, nextEmail),
        );
    }
  }
  webSocketMessage(socket: WebSocket, message: string | ArrayBuffer) {
    if (message === "snapshot") socket.send(JSON.stringify(this.snapshot()));
  }
  webSocketClose(socket: WebSocket, code: number, reason: string) {
    // Reserved status codes describe a disconnected peer and cannot be sent.
    socket.close([1005, 1006, 1015].includes(code) ? 1000 : code, reason);
    this.broadcast();
  }
  webSocketError(socket: WebSocket) {
    socket.close(1011, "Reconnect");
  }
}
