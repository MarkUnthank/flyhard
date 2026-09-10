import type Stripe from "stripe";
import {
  WRAP_START_PRICE,
  WRAP_PRICE_STEP,
  WRAP_VIDEOS,
  wrapCheckoutSchema,
  type CustomWrapSnapshot,
} from "../src/lib/custom-wrap";
import { money } from "../src/lib/auction";
import type { Env } from "./env";
import { HttpError, json, readJson } from "./http";
import { checkoutEmail, emailErrorCode } from "./outbid-email";

type WrapOrder = {
  id: string;
  request_id: string;
  amount: number;
  status: "pending" | "paid" | "expired" | "refund_pending" | "refunded";
  session_id: string | null;
  payment_id: string | null;
  refund_id: string | null;
  buyer_email: string | null;
  brand: string | null;
  sale_number: number | null;
  created_at: number;
  paid_at: number | null;
  notification_status: "pending" | "sent" | null;
  notification_attempts: number;
  next_attempt_at: number;
};
const CHECKOUT_LIFETIME = 31 * 60_000;

/** Shares the auction's durable SQLite transaction, revision and recovery alarm. */
export class CustomWrapOrders {
  private sql: SqlStorage;
  private maintenanceWork: Promise<void> | undefined;

  constructor(
    private ctx: DurableObjectState,
    private env: Env,
    private stripe: () => Stripe,
    private scheduleAlarm: () => Promise<void>,
    private broadcast: () => void,
  ) {
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS wrap_orders (
        id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
        amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        session_id TEXT UNIQUE, payment_id TEXT UNIQUE, refund_id TEXT,
        buyer_email TEXT, brand TEXT, sale_number INTEGER UNIQUE,
        created_at INTEGER NOT NULL, paid_at INTEGER,
        checked_at INTEGER NOT NULL DEFAULT 0,
        notification_status TEXT, notification_attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        notification_message_id TEXT, notification_error TEXT
      );
      CREATE INDEX IF NOT EXISTS wrap_status ON wrap_orders(status, checked_at);
      CREATE INDEX IF NOT EXISTS wrap_notification ON wrap_orders(notification_status, next_attempt_at);
    `);
  }

  private testMode() {
    return Boolean(this.env.STRIPE_API_KEY?.includes("_test_"));
  }
  private recipient() {
    return this.testMode()
      ? this.env.CUSTOM_WRAP_EMAIL_TEST_TO
      : this.env.CUSTOM_WRAP_EMAIL_TO;
  }
  snapshot(): CustomWrapSnapshot {
    const totals = this.sql
      .exec<{ count: number; total: number }>(
        "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS total FROM wrap_orders WHERE sale_number IS NOT NULL",
      )
      .one();
    return {
      amount: WRAP_START_PRICE + totals.count * WRAP_PRICE_STEP,
      soldCount: totals.count,
      totalRaised: totals.total,
      checkoutEnabled: Boolean(
        this.env.STRIPE_API_KEY &&
        this.env.STRIPE_WEBHOOK_SECRET &&
        this.env.EMAIL &&
        this.env.OUTBID_EMAIL_FROM &&
        checkoutEmail({ customer_email: this.recipient() }),
      ),
    };
  }
  hasWork() {
    return (
      this.sql
        .exec<{ count: number }>(
          "SELECT COUNT(*) AS count FROM wrap_orders WHERE status IN ('pending','refund_pending') OR notification_status = 'pending'",
        )
        .one().count > 0
    );
  }

  async checkout(request: Request) {
    const offer = this.snapshot();
    if (!offer.checkoutEnabled)
      throw new HttpError(
        503,
        "Custom wrap checkout is being connected. Please try again shortly.",
      );
    const parsed = wrapCheckoutSchema.safeParse(await readJson(request));
    if (!parsed.success)
      throw new HttpError(400, parsed.error.issues[0].message);
    const input = parsed.data;
    // Establish recovery before creating any order or making an external call.
    await this.scheduleAlarm();
    let order = this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE request_id = ?",
        input.requestId,
      )
      .toArray()[0];
    if (
      order &&
      (order.amount !== input.amount ||
        order.status !== "pending" ||
        order.created_at < Date.now() - CHECKOUT_LIFETIME)
    )
      throw new HttpError(
        409,
        "This checkout has ended. Please start a new checkout.",
      );
    const latest = this.snapshot();
    if (input.amount !== latest.amount)
      throw new HttpError(
        409,
        `A wrap just sold. The next one is ${money(latest.amount)} USD. Please check the new price and try again.`,
      );
    if (!order) {
      const id = crypto.randomUUID();
      this.sql.exec(
        "INSERT INTO wrap_orders (id, request_id, amount, created_at) VALUES (?,?,?,?)",
        id,
        input.requestId,
        latest.amount,
        Date.now(),
      );
      order = this.sql
        .exec<WrapOrder>("SELECT * FROM wrap_orders WHERE id = ?", id)
        .one();
    }
    const session = order.session_id
      ? await this.stripe().checkout.sessions.retrieve(order.session_id)
      : await this.stripe().checkout.sessions.create(
          {
            mode: "payment",
            payment_method_types: ["card"],
            line_items: [
              {
                quantity: 1,
                price_data: {
                  currency: "usd",
                  unit_amount: order.amount,
                  product_data: {
                    name: `The Driving Fly · Full custom wrap + ${WRAP_VIDEOS} videos`,
                    description: `We design a full custom wrap for the simulated Mini and release ${WRAP_VIDEOS} project videos featuring it. Production follows payment; we contact your checkout email to begin.`,
                  },
                },
              },
            ],
            client_reference_id: order.id,
            metadata: { custom_wrap_order_id: order.id },
            payment_intent_data: {
              capture_method: "automatic",
              metadata: { custom_wrap_order_id: order.id },
            },
            custom_fields: [
              {
                key: "brand",
                type: "text",
                label: { type: "custom", custom: "Brand or project name" },
                text: { maximum_length: 60 },
              },
            ],
            success_url: `${this.env.SITE_URL}/?wrap=success&session_id={CHECKOUT_SESSION_ID}#custom-wrap`,
            cancel_url: `${this.env.SITE_URL}/?wrap=cancelled#custom-wrap`,
            expires_at: Math.floor(order.created_at / 1000) + 31 * 60,
            custom_text: {
              submit: {
                message: `Full one-time payment is charged now for one custom wrap and ${WRAP_VIDEOS} videos. Production is scheduled by email. If another buyer pays this price first, we refund your payment in full. Terms: ${this.env.SITE_URL}/terms#custom-wrap`,
              },
            },
          },
          { idempotencyKey: `checkout:wrap:${order.id}` },
        );
    this.sql.exec(
      "UPDATE wrap_orders SET session_id = ? WHERE id = ?",
      session.id,
      order.id,
    );
    await this.scheduleAlarm();
    if (session.status !== "open" || !session.url)
      throw new HttpError(
        409,
        "This checkout has ended. Please start a new checkout.",
      );
    return json({ url: session.url, sessionId: session.id });
  }

  async confirm(request: Request) {
    const input = await readJson(request);
    if (
      typeof input?.sessionId !== "string" ||
      !/^cs_(test_|live_)?[A-Za-z0-9]+$/.test(input.sessionId) ||
      input.sessionId.length > 250
    )
      throw new HttpError(400, "Invalid checkout session.");
    const order = this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE session_id = ?",
        input.sessionId,
      )
      .toArray()[0];
    if (!order) throw new HttpError(404, "Checkout not found.");
    if (order.status === "pending")
      await this.fulfill(
        await this.stripe().checkout.sessions.retrieve(input.sessionId),
      );
    const updated = this.sql
      .exec<WrapOrder>("SELECT * FROM wrap_orders WHERE id = ?", order.id)
      .one();
    // A checkout URL is not permission to expose customer or payment details.
    return json({
      status: updated.status,
      orderNumber: updated.sale_number,
      offer: this.snapshot(),
    });
  }

  async fulfill(session: Stripe.Checkout.Session) {
    const order = this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE id = ?",
        session.metadata?.custom_wrap_order_id || "",
      )
      .toArray()[0];
    if (!order) return;
    if (session.payment_status !== "paid" || session.status !== "complete")
      return;
    if (
      session.mode !== "payment" ||
      session.currency !== "usd" ||
      session.amount_total !== order.amount ||
      session.client_reference_id !== order.id ||
      (order.session_id && session.id !== order.session_id) ||
      !session.payment_intent ||
      session.livemode !== !this.testMode()
    )
      throw new HttpError(400, "Payment does not match this custom wrap.");
    const paymentId =
      typeof session.payment_intent === "string"
        ? session.payment_intent
        : session.payment_intent.id;
    await this.scheduleAlarm();
    let changed = false;
    this.ctx.storage.transactionSync(() => {
      const current = this.sql
        .exec<WrapOrder>("SELECT * FROM wrap_orders WHERE id = ?", order.id)
        .one();
      // An authoritative late paid event also recovers an abandoned order whose
      // session creation response was lost before we could store its ID.
      if (current.status !== "pending" && current.status !== "expired") return;
      this.sql.exec(
        "UPDATE wrap_orders SET session_id = ?, payment_id = ?, buyer_email = ?, brand = ? WHERE id = ?",
        session.id,
        paymentId,
        checkoutEmail(session),
        session.custom_fields
          ?.find((field) => field.key === "brand")
          ?.text?.value?.slice(0, 60) || null,
        order.id,
      );
      const offer = this.snapshot();
      if (order.amount !== offer.amount) {
        this.sql.exec(
          "UPDATE wrap_orders SET status = 'refund_pending' WHERE id = ?",
          order.id,
        );
        return;
      }
      this.sql.exec(
        "UPDATE wrap_orders SET status = 'paid', sale_number = ?, paid_at = ?, notification_status = 'pending' WHERE id = ?",
        offer.soldCount + 1,
        Date.now(),
        order.id,
      );
      this.sql.exec(
        "UPDATE counters SET value = value + 1 WHERE name = 'revision'",
      );
      changed = true;
    });
    if (changed) this.broadcast();
    this.ctx.waitUntil(this.maintenance());
  }

  async reconcile() {
    const pending = this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE status = 'pending' AND session_id IS NOT NULL ORDER BY checked_at LIMIT 20",
      )
      .toArray();
    for (const order of pending) {
      try {
        const session = await this.stripe().checkout.sessions.retrieve(
          order.session_id!,
        );
        await this.fulfill(session);
        if (session.status === "expired")
          this.sql.exec(
            "UPDATE wrap_orders SET status = 'expired' WHERE id = ? AND status = 'pending'",
            order.id,
          );
      } catch {
        console.error("Custom wrap checkout will retry", order.id);
      }
      this.sql.exec(
        "UPDATE wrap_orders SET checked_at = ? WHERE id = ?",
        Date.now(),
        order.id,
      );
    }
    // Unknown session responses still recover via Stripe's metadata webhook.
    this.sql.exec(
      "UPDATE wrap_orders SET status = 'expired' WHERE status = 'pending' AND session_id IS NULL AND created_at < ?",
      Date.now() - 86_400_000,
    );
    await this.maintenance();
  }

  private async maintenance() {
    const work = (this.maintenanceWork ?? Promise.resolve())
      .catch(() => {})
      .then(() => this.processJobs());
    this.maintenanceWork = work;
    try {
      await work;
    } finally {
      if (this.maintenanceWork === work) this.maintenanceWork = undefined;
    }
  }
  private async processJobs() {
    for (const order of this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE status = 'refund_pending' LIMIT 20",
      )
      .toArray()) {
      try {
        const refund = order.refund_id
          ? await this.stripe().refunds.retrieve(order.refund_id)
          : await this.stripe().refunds.create(
              {
                payment_intent: order.payment_id!,
                metadata: {
                  custom_wrap_order_id: order.id,
                  reason: "Custom wrap price already purchased",
                },
              },
              { idempotencyKey: `refund:wrap:${order.id}` },
            );
        this.sql.exec(
          "UPDATE wrap_orders SET refund_id = ?, status = ? WHERE id = ?",
          refund.id,
          refund.status === "succeeded" ? "refunded" : "refund_pending",
          order.id,
        );
      } catch {
        console.error("Custom wrap refund will retry", order.id);
      }
    }
    if (!this.env.EMAIL || !this.env.OUTBID_EMAIL_FROM || !this.recipient())
      return;
    for (const order of this.sql
      .exec<WrapOrder>(
        "SELECT * FROM wrap_orders WHERE notification_status = 'pending' AND next_attempt_at <= ? ORDER BY paid_at LIMIT 20",
        Date.now(),
      )
      .toArray()) {
      try {
        const result = await this.env.EMAIL.send({
          from: { name: "The Driving Fly", email: this.env.OUTBID_EMAIL_FROM },
          to: this.recipient()!,
          subject: `${this.testMode() ? "[TEST] " : ""}${money(order.amount)} custom wrap purchased — #${order.sale_number}`,
          text: [
            this.testMode()
              ? "TEST PURCHASE — no real money was charged. Do not begin production."
              : "Payment confirmed. You can start working on the custom wrap now.",
            `Order: #${order.sale_number} (${order.id})`,
            `Brand / project: ${order.brand || "See Stripe checkout"}`,
            `Buyer email: ${order.buyer_email || "Missing — check the payment in Stripe before starting."}`,
            `Paid: ${money(order.amount)} USD, in full.`,
            `Deliverables: one full custom wrap for the simulated Mini and ${WRAP_VIDEOS} released project videos featuring it.`,
            "Next step: contact the buyer for their artwork and brief, and arrange production in purchase order.",
            `Payment: https://dashboard.stripe.com/${this.testMode() ? "test/" : ""}payments/${order.payment_id}`,
            `The next wrap is available immediately at ${money(this.snapshot().amount)} USD.`,
          ].join("\n\n"),
          headers: {
            "X-Custom-Wrap-Order": order.id,
            "Auto-Submitted": "auto-generated",
          },
        });
        this.sql.exec(
          "UPDATE wrap_orders SET notification_status = 'sent', notification_message_id = ?, notification_error = NULL WHERE id = ?",
          result.messageId,
          order.id,
        );
      } catch (error) {
        this.sql.exec(
          "UPDATE wrap_orders SET notification_attempts = notification_attempts + 1, next_attempt_at = ?, notification_error = ? WHERE id = ?",
          Date.now() +
            Math.min(
              3_600_000,
              60_000 * 2 ** Math.min(order.notification_attempts, 6),
            ),
          emailErrorCode(error),
          order.id,
        );
        console.error(
          "Custom wrap purchase email will retry",
          order.id,
          emailErrorCode(error),
        );
      }
    }
  }
}
