"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { ArrowUpRight, LockKeyhole, Minus, Plus, X } from "lucide-react";
import {
  dollarsToCents,
  minimumBid,
  money,
  type AuctionSnapshot,
  type CheckoutConfirmation,
  type Slot,
} from "@/lib/auction";
import ArtworkEditor, { type PreparedArtwork } from "./artwork-editor";
import type { View } from "./car-viewer";
import { rememberCheckout } from "@/lib/checkout-recovery";

const CarViewer = dynamic(() => import("./car-viewer"), {
  ssr: false,
  loading: () => (
    <div className="viewer-shell model-loading">Preparing your spot…</div>
  ),
});

export default function BidDialog({
  slot,
  snapshot,
  onClose,
  purchase,
  initialAmount,
  onComplete,
}: {
  slot: Slot;
  snapshot: AuctionSnapshot;
  onClose: () => void;
  purchase?: { sessionId: string; amount: number };
  initialAmount?: number;
  onComplete: (result: CheckoutConfirmation) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const bidInput = useRef<HTMLInputElement>(null);
  const current = snapshot.placements[slot.id];
  const minimum = minimumBid(current?.amount);
  const [amount, setAmount] = useState(
    (
      (initialAmount && initialAmount >= minimum ? initialAmount : minimum) /
      100
    )
      .toFixed(2)
      .replace(/\.00$/, ""),
  );
  const [brand, setBrand] = useState("");
  const [message, setMessage] = useState("");
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState("");
  const [artwork, setArtwork] = useState<Blob | null>(null);
  const [logo, setLogo] = useState<Blob | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const checkoutAttempt = useRef<{
    signature: string;
    requestId: string;
    token?: string;
    logoToken?: string;
  }>({ signature: "", requestId: "" });
  const cents = dollarsToCents(amount);
  const maximum = 99_999_999;
  function stepAmount(direction: -1 | 1) {
    if (busy || minimum > maximum) return;
    const next =
      cents === null
        ? minimum
        : Math.min(maximum, Math.max(minimum, cents + direction * 100));
    setAmount((next / 100).toFixed(next % 100 ? 2 : 0));
  }

  const highestBid = Math.max(
    0,
    ...Object.values(snapshot.placements).map((placement) => placement.amount),
  );
  const featuredMinimum = Math.max(minimum, highestBid + 100);
  const validBid = cents !== null && cents > 0 && cents <= 99_999_999;
  const featuredDifference = cents === null ? 0 : featuredMinimum - cents;
  const willBeFeatured = validBid && cents >= featuredMinimum;
  const previewPlacements = useMemo(
    () =>
      preview
        ? {
            ...snapshot.placements,
            [slot.id]: {
              id: "local-preview",
              slotId: slot.id,
              brand: "Your artwork",
              message: "",
              url: "",
              amount: 0,
              textureUrl: preview,
              logoUrl: preview,
              publishedAt: 0,
            },
          }
        : snapshot.placements,
    [snapshot.placements, slot.id, preview],
  );

  useEffect(() => {
    const element = dialog.current!;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  const prepareArtwork = useCallback((next: PreparedArtwork) => {
    setArtwork(next.blob);
    setLogo(next.logo ?? null);
    if (next.url !== undefined) setPreview(next.url);
  }, []);

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (purchase) {
      if (!artwork || !logo || !agreed) {
        setError("Add your artwork and confirm you have permission to use it.");
        return;
      }
    } else if (!cents || cents < minimum || cents > maximum) {
      setError(`The minimum for this spot is now ${money(minimum)}.`);
      return;
    }
    setBusy(true);
    try {
      if (purchase) {
        const signature = JSON.stringify([
          brand.trim(),
          message.trim(),
          url.trim(),
          preview,
        ]);
        if (checkoutAttempt.current.signature !== signature)
          checkoutAttempt.current = { signature, requestId: "" };
        const attempt = checkoutAttempt.current;
        async function upload(image: Blob) {
          const response = await fetch("/api/artwork", {
            method: "POST",
            headers: { "Content-Type": "image/png" },
            body: image,
          });
          const data = (await response.json()) as {
            error?: string;
            token: string;
          };
          if (!response.ok)
            throw new Error(
              data.error || "Artwork upload failed. Please try again.",
            );
          return data.token;
        }
        if (!attempt.token) attempt.token = await upload(artwork!);
        if (!attempt.logoToken) attempt.logoToken = await upload(logo!);
        const response = await fetch("/api/checkout/details", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId: purchase.sessionId,
            brand: brand.trim(),
            message: message.trim(),
            url: url.trim(),
            artworkToken: attempt.token,
            logoToken: attempt.logoToken,
            acceptedTerms: agreed,
          }),
        });
        const data = (await response.json()) as CheckoutConfirmation & {
          error?: string;
        };
        if (!response.ok) {
          if (response.status === 409) {
            const confirmation = await fetch("/api/checkout/confirm", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ sessionId: purchase.sessionId }),
            });
            if (confirmation.ok) {
              const result =
                (await confirmation.json()) as CheckoutConfirmation;
              if (
                ["won", "outbid", "refunded", "refund_pending"].includes(
                  result.status,
                )
              ) {
                onComplete(result);
                return;
              }
            }
          }
          if (response.status === 400)
            checkoutAttempt.current = { signature: "", requestId: "" };
          throw new Error(
            data.error || "Your details could not be saved. Please try again.",
          );
        }
        onComplete(data);
        return;
      }
      const signature = JSON.stringify([slot.id, cents]);
      if (checkoutAttempt.current.signature !== signature)
        checkoutAttempt.current = { signature, requestId: crypto.randomUUID() };
      const response = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requestId: checkoutAttempt.current.requestId,
          slotId: slot.id,
          amount: cents,
          acceptedTerms: true,
        }),
      });
      const data = (await response.json()) as {
        error?: string;
        url: string;
        sessionId: string;
      };
      if (!response.ok) {
        if (response.status === 409)
          checkoutAttempt.current = { signature: "", requestId: "" };
        throw new Error(data.error || "Checkout failed. Please try again.");
      }
      const target = new URL(data.url);
      if (
        target.protocol !== "https:" ||
        target.hostname !== "checkout.stripe.com"
      )
        throw new Error("Checkout could not be opened.");
      rememberCheckout(data.sessionId);
      window.location.assign(target.href);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Please try again.");
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="bid-dialog"
      aria-labelledby="checkout-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current && !busy) onClose();
      }}
    >
      <div className="checkout-layout">
        <button
          className="close-dialog"
          aria-label="Close checkout"
          onClick={onClose}
          disabled={busy}
        >
          <X size={20} />
        </button>
        <section
          className="checkout-visual"
          aria-label="Your selected advertising spot"
        >
          <div className="checkout-visual-heading">
            <span className="eyebrow">A LITTLE PIECE OF THE EXPERIMENT</span>
            <h3>Your brand. Right here.</h3>
            <p>
              Spot {slot.id.slice(3)} · {slot.name}
            </p>
          </div>
          <CarViewer
            placements={previewPlacements}
            selected={slot.id}
            view={slot.face as View}
            onSelect={() => {}}
            focusOnSelected
            previewing={Boolean(preview)}
          />
          <div className="checkout-preview-caption" aria-live="polite">
            <span className="preview-swatch" />
            <p>
              {preview
                ? "Your artwork, fitted to the actual spot. Only you can see this preview."
                : purchase
                  ? "Your spot is outlined in green. Add artwork to see it on the car."
                  : "Your spot is outlined in green. You’ll add your artwork after payment."}
            </p>
            <span className="spot-dimensions">
              {Math.round(slot.width_m * 100)} ×{" "}
              {Math.round(slot.height_m * 100)} cm
            </span>
          </div>
        </section>
        <div className="dialog-content">
          <div className="eyebrow">
            <span className="slot-number">{slot.id.slice(3)}</span> YOUR NEXT
            PARKING SPOT
          </div>
          <h2 id="checkout-title">{slot.name}</h2>
          <ol className="checkout-steps" aria-label="Claim your spot">
            {["Your bid", "Payment", "Your details"].map((label, index) => (
              <li
                key={label}
                aria-current={index === (purchase ? 2 : 0) ? "step" : undefined}
                className={purchase && index < 2 ? "is-complete" : ""}
              >
                <span>{purchase && index < 2 ? "✓" : index + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          <p className="dialog-intro">
            {purchase
              ? "Payment received. Let’s make this spot yours."
              : "Choose your bid. Add your brand and artwork after payment."}
          </p>
          {purchase ? (
            <div className="payment-received">
              <span>Paid securely</span>
              <strong>{money(purchase.amount)}</strong>
            </div>
          ) : (
            <div className="current-owner">
              <span>
                {current ? (
                  <>
                    Currently held by <strong>{current.brand}</strong>
                  </>
                ) : (
                  <>
                    <span className="tiny-dot" /> Be the first on this spot
                  </>
                )}
              </span>
              <strong>{current ? money(current.amount) : "From $1"}</strong>
            </div>
          )}
          <form onSubmit={submit}>
            <fieldset disabled={busy}>
              {!purchase && (
                <>
                  <div className="field-heading">
                    <label htmlFor="bid-amount">Your one-time bid</label>
                    <span>Minimum {money(minimum)}</span>
                  </div>
                  <div className="amount-input">
                    <span>$</span>
                    <input
                      id="bid-amount"
                      type="number"
                      min={minimum / 100}
                      max={maximum / 100}
                      step="0.01"
                      onKeyDown={(event) => {
                        if (
                          event.key === "ArrowUp" ||
                          event.key === "ArrowDown"
                        ) {
                          event.preventDefault();
                          stepAmount(event.key === "ArrowUp" ? 1 : -1);
                        }
                      }}
                      ref={bidInput}
                      inputMode="decimal"
                      value={amount}
                      onChange={(event) => setAmount(event.target.value)}
                      required
                      aria-describedby={
                        validBid ? "bid-help featured-sponsor-help" : "bid-help"
                      }
                    />
                    <div className="amount-controls">
                      <button
                        type="button"
                        aria-label="Decrease bid by one dollar"
                        aria-controls="bid-amount"
                        disabled={
                          minimum > maximum ||
                          cents === null ||
                          cents <= minimum
                        }
                        onClick={() => stepAmount(-1)}
                      >
                        <Minus size={18} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label="Increase bid by one dollar"
                        aria-controls="bid-amount"
                        disabled={
                          minimum > maximum ||
                          (cents !== null && cents >= maximum)
                        }
                        onClick={() => stepAmount(1)}
                      >
                        <Plus size={18} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                  <p id="bid-help" className="field-help">
                    {current
                      ? "Bid at least $1 more than the current owner."
                      : "Start at $1, or pay any amount you like."}{" "}
                    All prices in USD.
                  </p>
                  <div
                    id="featured-sponsor-help"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    {validBid && featuredMinimum <= maximum && (
                      <div
                        className={`featured-sponsor-callout${willBeFeatured ? " is-qualified" : ""}`}
                      >
                        <span className="featured-sponsor-label">
                          Become the featured sponsor
                        </span>
                        <strong>
                          {willBeFeatured
                            ? "You will be the featured sponsor"
                            : `Bid ${money(featuredDifference)} more`}
                        </strong>
                        <p>
                          {willBeFeatured
                            ? "Once you’ve paid and published your details."
                            : `Minimum ${money(featuredMinimum)} to be the featured sponsor.`}
                        </p>
                        {!willBeFeatured && (
                          <button
                            type="button"
                            className="featured-sponsor-update"
                            onClick={() => {
                              setAmount(
                                (featuredMinimum / 100).toFixed(
                                  featuredMinimum % 100 ? 2 : 0,
                                ),
                              );
                              bidInput.current?.focus();
                            }}
                          >
                            Update my bid
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="amount-presets">
                    {[1, 5, 10, 25]
                      .filter((value) => value * 100 >= minimum)
                      .map((value) => (
                        <button
                          type="button"
                          key={value}
                          className={cents === value * 100 ? "active" : ""}
                          onClick={() => setAmount(String(value))}
                        >
                          {money(value * 100)}
                        </button>
                      ))}
                  </div>
                </>
              )}
              {purchase && (
                <>
                  <label className="field-label" htmlFor="brand">
                    Brand or project name
                  </label>
                  <input
                    id="brand"
                    placeholder="Something worth putting on a car"
                    value={brand}
                    maxLength={60}
                    onChange={(event) => setBrand(event.target.value)}
                    required
                  />
                  <label className="field-label" htmlFor="brand-url">
                    Website
                  </label>
                  <input
                    id="brand-url"
                    type="url"
                    placeholder="https://your-website.com"
                    value={url}
                    maxLength={500}
                    onChange={(event) => setUrl(event.target.value)}
                    required
                  />
                  <label className="field-label" htmlFor="brand-message">
                    Your message{" "}
                    <span className="optional-label">(optional)</span>
                  </label>
                  <input
                    id="brand-message"
                    placeholder="A little introduction to what you do"
                    value={message}
                    maxLength={140}
                    onChange={(event) => setMessage(event.target.value)}
                    aria-describedby="message-help"
                  />
                  <p id="message-help" className="field-help message-help">
                    <span>
                      Shown with your logo and website in “Riding with us”.
                    </span>
                    <span>{message.length}/140</span>
                  </p>
                  <ArtworkEditor
                    ratio={slot.width_m / slot.height_m}
                    disabled={busy}
                    onChange={prepareArtwork}
                    onError={setError}
                  />
                  <label className="terms-checkbox">
                    <input
                      type="checkbox"
                      checked={agreed}
                      onChange={(event) => setAgreed(event.target.checked)}
                      required
                    />
                    <span>
                      I own or can use this artwork and accept the{" "}
                      <a href="/terms" target="_blank">
                        placement terms
                      </a>
                      . Publish my ad with these details and this artwork.
                    </span>
                  </label>
                </>
              )}
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              {!purchase && !snapshot.paymentsEnabled && (
                <p className="checkout-notice">
                  Payments aren’t open yet. Please check back soon.
                </p>
              )}
              <button
                className="primary checkout-button"
                type="submit"
                disabled={
                  busy ||
                  (purchase
                    ? !artwork || !logo || !agreed
                    : !snapshot.paymentsEnabled ||
                      !cents ||
                      cents < minimum ||
                      cents > maximum)
                }
              >
                {busy ? (
                  purchase ? (
                    "Publishing your spot…"
                  ) : (
                    "Opening secure checkout…"
                  )
                ) : (
                  <>
                    {purchase
                      ? "Publish my spot"
                      : `Claim this spot${cents ? ` for ${money(cents)}` : ""}`}
                    <ArrowUpRight size={18} />
                  </>
                )}
              </button>
              {purchase ? (
                <p className="stripe-note">
                  No further payment. Your ad goes live when you publish it.
                </p>
              ) : (
                <p className="checkout-terms">
                  By continuing, you accept the{" "}
                  <a href="/terms" target="_blank" rel="noreferrer">
                    placement terms
                  </a>
                  . Your ad stays until someone bids at least $1 more and
                  publishes their ad. No guaranteed duration or refund once
                  live. If your bid is beaten before publication, we’ll refund
                  you in full.
                </p>
              )}
              {!purchase && (
                <p className="stripe-note">
                  <LockKeyhole size={12} /> Secure checkout with Stripe{" "}
                  {snapshot.paymentMode === "test" && "· Test mode"}
                </p>
              )}
              {purchase && (
                <p className="stripe-note">
                  <button
                    type="button"
                    className="checkout-save-link"
                    onClick={async () => {
                      const link = new URL(
                        `/?checkout=success&session_id=${encodeURIComponent(purchase.sessionId)}#live-auction`,
                        location.origin,
                      );
                      try {
                        await navigator.clipboard.writeText(link.href);
                        setLinkCopied(true);
                      } catch {
                        history.replaceState({}, "", link.href);
                        setError(
                          "Bookmark this page’s address to finish later.",
                        );
                      }
                    }}
                  >
                    {linkCopied
                      ? "Private link copied"
                      : "Copy a private link to finish later"}
                  </button>
                </p>
              )}
            </fieldset>
          </form>
        </div>
      </div>
    </dialog>
  );
}
