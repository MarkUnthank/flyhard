"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { ArrowUpRight, LockKeyhole, X } from "lucide-react";
import {
  dollarsToCents,
  minimumBid,
  money,
  type AuctionSnapshot,
  type Slot,
} from "@/lib/auction";
import ArtworkEditor, { type PreparedArtwork } from "./artwork-editor";
import type { View } from "./car-viewer";

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
}: {
  slot: Slot;
  snapshot: AuctionSnapshot;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const current = snapshot.placements[slot.id];
  const minimum = minimumBid(current?.amount);
  const [amount, setAmount] = useState(
    (minimum / 100).toFixed(minimum % 100 ? 2 : 0),
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
  const checkoutAttempt = useRef<{
    signature: string;
    requestId: string;
    token?: string;
    logoToken?: string;
  }>({ signature: "", requestId: "" });
  const cents = dollarsToCents(amount);
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
    if (!cents || cents < minimum) {
      setError(`The minimum for this spot is now ${money(minimum)}.`);
      return;
    }
    if (!artwork || !logo) {
      setError("Add your logo before continuing.");
      return;
    }
    if (!agreed) {
      setError("Please accept the placement terms.");
      return;
    }
    setBusy(true);
    try {
      const signature = JSON.stringify([
        slot.id,
        cents,
        brand.trim(),
        message.trim(),
        url.trim(),
        preview,
      ]);
      if (checkoutAttempt.current.signature !== signature)
        checkoutAttempt.current = { signature, requestId: crypto.randomUUID() };
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
        if (!response.ok) throw new Error(data.error);
        return data.token;
      }
      if (!attempt.token) attempt.token = await upload(artwork);
      if (!attempt.logoToken) attempt.logoToken = await upload(logo);
      const response = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requestId: attempt.requestId,
          slotId: slot.id,
          amount: cents,
          brand: brand.trim(),
          message: message.trim(),
          url: url.trim(),
          artworkToken: attempt.token,
          logoToken: attempt.logoToken,
          acceptedTerms: agreed,
        }),
      });
      const data = (await response.json()) as { error?: string; url: string };
      if (!response.ok) {
        if (response.status === 409)
          checkoutAttempt.current = { signature: "", requestId: "" };
        throw new Error(data.error);
      }
      const target = new URL(data.url);
      if (
        target.protocol !== "https:" ||
        target.hostname !== "checkout.stripe.com"
      )
        throw new Error("Checkout could not be opened.");
      window.location.assign(target.href);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Checkout failed. Please try again.",
      );
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
                : "Your spot is outlined in green. Add artwork to see it on the car."}
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
          <p className="dialog-intro">A little space for your big idea.</p>
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
          <form onSubmit={submit}>
            <fieldset disabled={busy}>
              <div className="field-heading">
                <label htmlFor="bid-amount">Your one-time bid</label>
                <span>Minimum {money(minimum)}</span>
              </div>
              <div className="amount-input">
                <span>$</span>
                <input
                  id="bid-amount"
                  inputMode="decimal"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  required
                  aria-describedby="bid-help"
                />
              </div>
              <p id="bid-help" className="field-help">
                {current
                  ? "Bid at least $1 more than the current owner."
                  : "Start at $1, or pay any amount you like."}{" "}
                All prices in USD.
              </p>
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
                Your message <span className="optional-label">(optional)</span>
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
                  . My ad stays until someone pays at least $1 more, with no
                  guaranteed duration or refund after it goes live.
                </span>
              </label>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              {!snapshot.paymentsEnabled && (
                <p className="checkout-notice">
                  Payments aren’t open yet. You can explore the car and preview
                  your artwork.
                </p>
              )}
              <button
                className="primary checkout-button"
                type="submit"
                disabled={
                  busy ||
                  !snapshot.paymentsEnabled ||
                  !artwork ||
                  !cents ||
                  cents < minimum
                }
              >
                {busy ? (
                  "Opening secure checkout…"
                ) : (
                  <>
                    Claim this spot {cents ? `for ${money(cents)}` : ""}
                    <ArrowUpRight size={18} />
                  </>
                )}
              </button>
              <p className="stripe-note">
                We’ll email your Stripe checkout address if you’re outbid.
              </p>
              <p className="stripe-note">
                <LockKeyhole size={12} /> Secure checkout with Stripe{" "}
                {snapshot.paymentMode === "test" && "· Test mode"}
              </p>
            </fieldset>
          </form>
        </div>
      </div>
    </dialog>
  );
}
