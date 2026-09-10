"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, Sparkles } from "lucide-react";
import { money, type AuctionSnapshot } from "@/lib/auction";
import { WRAP_PRICE_STEP, WRAP_VIDEOS } from "@/lib/custom-wrap";
import styles from "./custom-wrap-offer.module.css";

export default function CustomWrapOffer({
  snapshot,
  loaded,
  accept,
}: {
  snapshot: AuctionSnapshot;
  loaded: boolean;
  accept: (snapshot: AuctionSnapshot) => void;
}) {
  const offer = snapshot.customWrap;
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const request = useRef<{ id: string; amount: number } | null>(null);
  const shell = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = shell.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          element.dataset.visible = "true";
          observer.disconnect();
        }
      },
      { threshold: 0.12 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (!params.has("wrap")) return;
    if (params.get("wrap") === "cancelled") {
      setMessage("Checkout cancelled. Your custom wrap hasn’t been purchased.");
      history.replaceState({}, "", "/#custom-wrap");
      return;
    }
    const sessionId = params.get("session_id");
    if (!sessionId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const confirm = async () => {
      setMessage("Checking your payment with Stripe…");
      try {
        const response = await fetch("/api/custom-wrap/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId }),
        });
        const data = (await response.json()) as {
          status: string;
          orderNumber: number | null;
          error?: string;
        };
        if (stopped) return;
        if (!response.ok) throw new Error(data.error);
        const messages: Record<string, string> = {
          paid: `You’re in. Custom wrap #${data.orderNumber} is paid in full. We’ll contact your checkout email to get your brief and arrange your wrap and ${WRAP_VIDEOS} videos.`,
          refund_pending:
            "Another buyer purchased that price first. We’re arranging a full refund. You can purchase the next wrap at the price below.",
          refunded:
            "Another buyer purchased that price first. Your payment has been refunded in full. You can purchase the next wrap at the price below.",
          expired:
            "Your checkout expired. You can start again at the current price below.",
        };
        if (messages[data.status]) {
          setMessage(messages[data.status]);
          history.replaceState({}, "", "/#custom-wrap");
          const refresh = await fetch("/api/auction", { cache: "no-store" });
          if (refresh.ok && !stopped) accept(await refresh.json());
        } else if (++attempts < 20) timer = setTimeout(confirm, 3000);
        else
          setMessage(
            "Your payment is still being checked. You can close this page; confirmed purchases are processed automatically. Keep your Stripe receipt.",
          );
      } catch {
        if (!stopped)
          setMessage(
            "We couldn’t check your payment yet. Keep your Stripe receipt; confirmed purchases are processed automatically.",
          );
      }
    };
    void confirm();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
    // Confirm the checkout return once; subsequent prices arrive over live updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function checkout() {
    if (busy) return;
    setBusy(true);
    setError("");
    if (!request.current || request.current.amount !== offer.amount)
      request.current = { id: crypto.randomUUID(), amount: offer.amount };
    try {
      const response = await fetch("/api/custom-wrap/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requestId: request.current.id,
          amount: request.current.amount,
          acceptedTerms: true,
        }),
      });
      const data = (await response.json()) as { url?: string; error?: string };
      if (!response.ok || !data.url) {
        if (response.status === 409) request.current = null;
        throw new Error(
          data.error || "Checkout couldn’t open. Please try again.",
        );
      }
      location.assign(data.url);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Checkout couldn’t open. Please try again.",
      );
      setBusy(false);
      try {
        const response = await fetch("/api/auction", { cache: "no-store" });
        if (response.ok) accept(await response.json());
      } catch {
        /* Keep the latest confirmed offer. */
      }
    }
  }

  return (
    <section
      className={styles.section}
      id="custom-wrap"
      aria-labelledby="custom-wrap-title"
      ref={shell}
    >
      <div className={styles.shell}>
        <div className={styles.card}>
          <div className={styles.sheen} aria-hidden="true" />
          <div className={styles.topline}>
            <span className={styles.badge}>
              <Sparkles size={14} strokeWidth={1.4} /> THE FULL CUSTOM WRAP
            </span>
            <span className={styles.edition}>
              {loaded
                ? `NO. ${String(offer.soldCount + 1).padStart(3, "0")}`
                : "THE NEXT CHAPTER"}
            </span>
          </div>
          <div className={styles.content}>
            <div className={styles.pitch}>
              <h2 id="custom-wrap-title">
                Your brand.
                <br />
                <span>
                  The whole
                  <br className={styles.desktopBreak} /> damn car.
                </span>
              </h2>
              <p>
                Go all in. We design a full custom wrap for the fly’s Mini, then
                release <strong>{WRAP_VIDEOS} videos</strong> with your brand
                along for the ride.
              </p>
              <div className={styles.signature}>
                ONE TINY DRIVER. A MASSIVE ENTRANCE.
              </div>
            </div>
            <div className={styles.purchaseShell}>
              <div className={styles.purchase}>
                <span className={styles.priceLabel}>YOUR CUSTOM WRAP</span>
                <div className={styles.price} aria-live="polite">
                  {loaded ? money(offer.amount) : "$10,000"}
                </div>
                <span className={styles.currency}>
                  USD · one payment · charged in full at checkout
                </span>
                <div className={styles.includes}>
                  <span>
                    <Check size={16} strokeWidth={1.5} /> A full wrap, designed
                    for your brand
                  </span>
                  <span>
                    <Check size={16} strokeWidth={1.5} /> {WRAP_VIDEOS} released
                    videos featuring your wrap
                  </span>
                  <span>
                    <Check size={16} strokeWidth={1.5} /> Direct creative
                    collaboration with us
                  </span>
                </div>
                <button
                  className={styles.cta}
                  onClick={() => void checkout()}
                  disabled={busy || !loaded || !offer.checkoutEnabled}
                >
                  {busy ? "Opening Stripe…" : "Make it yours"}
                  <span>
                    <ArrowUpRight size={21} strokeWidth={1.5} />
                  </span>
                </button>
                <p className={styles.nextPrice}>
                  Next purchase:{" "}
                  <strong>{money(offer.amount + WRAP_PRICE_STEP)}</strong>
                  <br />
                  The price goes up $1 every time a wrap sells.
                </p>
                <p className={styles.terms}>
                  By continuing, you agree to the{" "}
                  <a href="/terms#custom-wrap">custom wrap terms</a>. Secure
                  checkout by Stripe.
                </p>
                {loaded && !offer.checkoutEnabled && (
                  <p className={styles.notice}>
                    Checkout is being connected. Please check back shortly.
                  </p>
                )}
                {snapshot.paymentMode === "test" && (
                  <p className={styles.notice}>
                    Test checkout · no real payment
                  </p>
                )}
                {error && (
                  <p className={styles.notice} role="alert">
                    {error}
                  </p>
                )}
              </div>
            </div>
          </div>
          <ol className={styles.process}>
            <li>
              <span>01</span>
              <div>
                <strong>You make it official.</strong>
                <p>Pay once. Your project joins the queue.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>We make it yours.</strong>
                <p>We get your brief and design the full wrap.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>The fly takes it for a spin.</strong>
                <p>We release {WRAP_VIDEOS} videos featuring your wrap.</p>
              </div>
            </li>
          </ol>
          <p className={styles.footer}>
            A custom livery for our simulated Mini. Production follows purchase,
            with timing arranged by email. The next spot opens immediately.
          </p>
          {message && (
            <div className={styles.status} role="status">
              <Check size={20} strokeWidth={1.5} />
              <p>{message}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
