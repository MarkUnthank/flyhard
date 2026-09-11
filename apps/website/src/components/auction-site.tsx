"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Search,
  X,
} from "lucide-react";
import {
  activeSlots,
  compareSlots,
  minimumBid,
  money,
  rankPlacements,
  type Slot,
  type AuctionSnapshot,
  type CheckoutConfirmation,
  slots as allSlots,
} from "@/lib/auction";
import { useAuction } from "./use-auction";
import FlyMark from "./fly-mark";
import MediaSection from "./media-section";
import SiteHeader from "./site-header";
import SiteFooter from "./site-footer";
import HistoricalBids from "./historical-bids";
import BidDialog from "./bid-dialog";
import {
  savedCheckouts,
  rememberCheckout,
  forgetCheckout,
} from "@/lib/checkout-recovery";
import CustomWrapOffer from "./custom-wrap-offer";
import type { View } from "./car-viewer";

const CarViewer = dynamic(() => import("./car-viewer"), {
  ssr: false,
  loading: () => (
    <div className="viewer-shell model-loading">Preparing the garage…</div>
  ),
});
const views: { id: View; label: string }[] = [
  { id: "perspective", label: "3D view" },
  { id: "left", label: "Left" },
  { id: "right", label: "Right" },
  { id: "top", label: "Top" },
  { id: "front", label: "Front" },
  { id: "back", label: "Rear" },
];
const faqs = [
  [
    "Wait. Is a fly actually driving?",
    "It’s a research experiment using a neural model built from a fruit fly’s measured connectome. The model moves a simulated fly’s legs, which physically turn a steering wheel in CARLA. The steering works; speed and turn requests are currently scripted. Learning to drive from vision is still ahead.",
  ],
  [
    "How long does my ad stay on the car?",
    "Until someone pays more for the same spot. There’s no end date and no guaranteed minimum time. An empty spot starts at $1; after that, a new bid must be at least $1 higher. You pay your full bid once, with any applicable tax shown at checkout.",
  ],
  [
    "What happens when someone outbids me?",
    "Their artwork replaces yours once they have paid and published their details. We’ll email your Stripe checkout address with a link to bid again. Your brand remains in the recent supporter history. A placement that has already gone live isn’t refunded just because it is outbid.",
  ],
  [
    "What if two people pay at the same time?",
    "Payments are checked against the latest confirmed price. If your payment is already beaten before your artwork is published, we automatically request a full refund. If your artwork went live first and was then replaced, that is a normal outbid.",
  ],
  [
    "Where will my logo appear?",
    "On your chosen spot on the live, interactive Mini on this website, with your name and a link in the auction. The current livery is available for our future project recordings, but we don’t guarantee video appearances, audience numbers, clicks, or a return on your spend.",
  ],
  [
    "What can I put on my spot?",
    "A logo, project, or original design you have permission to use. Upload a PNG, JPG, or WebP, choose its background, and check the preview after payment, before publishing your spot. Illegal, hateful, explicit, misleading, or infringing ads can be removed under the placement terms.",
  ],
  ["Is this a joke?", "100% yes."],
  ["Is this joke funny?", "Not in the slightest."],
];

export default function AuctionSite() {
  const { snapshot, connected, loaded, accept } = useAuction();
  const [manualView, setManualView] = useState<View | null>(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Slot | null>(null);
  const [status, setStatus] = useState("");
  const [purchases, setPurchases] = useState<
    ({ sessionId: string } & CheckoutConfirmation)[]
  >([]);
  const [editingPurchase, setEditingPurchase] = useState<
    ({ sessionId: string } & CheckoutConfirmation) | null
  >(null);
  const [initialAmount, setInitialAmount] = useState<number>();
  const [checkoutRetry, setCheckoutRetry] = useState(0);
  const [canRetryCheckout, setCanRetryCheckout] = useState(false);
  const [sort, setSort] = useState("price");
  const [showAll, setShowAll] = useState(false);
  const slots = useMemo(
    () => activeSlots(snapshot.placements),
    [snapshot.placements],
  );
  const taken = Object.keys(snapshot.placements).length;
  const entryBid = Math.min(
    ...slots.map((slot) => minimumBid(snapshot.placements[slot.id]?.amount)),
  );
  const entrySlot = slots.find(
    (slot) => minimumBid(snapshot.placements[slot.id]?.amount) === entryBid,
  );
  const filtered = useMemo(
    () =>
      slots
        .filter(
          (slot) =>
            (filter === "all" ||
              slot.face === filter ||
              (filter === "available" && !snapshot.placements[slot.id])) &&
            `${slot.name} ${slot.id} ${snapshot.placements[slot.id]?.brand || ""} ${snapshot.placements[slot.id]?.url || ""} ${snapshot.placements[slot.id]?.message || ""}`
              .toLowerCase()
              .includes(query.toLowerCase()),
        )
        .sort((a, b) =>
          compareSlots(a, b, snapshot.placements, sort === "price"),
        ),
    [filter, slots, query, sort, snapshot.placements],
  );
  const displayed =
    showAll || filter !== "all" || query ? filtered : filtered.slice(0, 12);
  const highestBid = rankPlacements(snapshot.placements)[0];
  // The hero CTA aims at the priciest placement, and falls back to the cheapest
  // way onto the car while the livery is still empty.
  const heroSlot =
    slots.find((slot) => slot.id === highestBid?.slotId) || entrySlot;
  const fundingTarget = 100_000;
  const fundingPercent = (snapshot.totalRaised / fundingTarget) * 100;
  const fundingLabel = `${Number(fundingPercent.toFixed(1))}%`;
  const view = manualView ?? "perspective";

  const paymentMessages: Partial<
    Record<CheckoutConfirmation["status"], string>
  > = {
    won: "You’re on the car. Your payment is confirmed and your artwork is live.",
    outbid:
      "Your artwork went live, and another supporter has since outbid you. Thank you for being part of the experiment.",
    refund_pending:
      "Someone beat your bid before your ad went live. We’re arranging a full refund.",
    refunded:
      "Someone beat your bid before your ad went live. Your payment has been refunded.",
    expired:
      "This checkout has expired. You can start a new bid whenever you’re ready.",
  };
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.has("wrap")) return;
    const wasCancelled = params.get("checkout") === "cancelled";
    if (wasCancelled)
      setStatus("Checkout cancelled. You can update your bid and try again.");
    const returnSession = params.get("session_id");
    if (returnSession) rememberCheckout(returnSession);
    const sessionIds = [
      ...new Set([
        ...(returnSession ? [returnSession] : []),
        ...savedCheckouts(),
      ]),
    ];
    let cancelled = false;
    let opened = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    setCanRetryCheckout(false);
    const confirm = async (sessionId: string, attempts = 0) => {
      if (sessionId === returnSession && attempts === 0)
        setStatus("Checking your payment with Stripe…");
      try {
        const response = await fetch("/api/checkout/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId }),
        });
        const data = (await response.json()) as CheckoutConfirmation & {
          error?: string;
        };
        if (cancelled) return;
        if (!response.ok) {
          if (response.status === 404 || response.status === 400) {
            forgetCheckout(sessionId);
            if (sessionId !== returnSession) return;
          }
          throw new Error(data.error);
        }
        accept(data.snapshot);
        if (data.status === "awaiting_details") {
          const purchase = { ...data, sessionId };
          setPurchases((previous) => [
            ...previous.filter((item) => item.sessionId !== sessionId),
            purchase,
          ]);
          if (!opened && !wasCancelled) {
            opened = true;
            setSelected(null);
            setEditingPurchase(purchase);
          }
          setStatus(
            "Payment received. Add your brand and artwork to publish your spot.",
          );
        } else if (data.status === "pending") {
          if (sessionId !== returnSession) return;
          if (attempts < 19)
            timers.push(
              setTimeout(() => void confirm(sessionId, attempts + 1), 3000),
            );
          else if (sessionId === returnSession) {
            setStatus(
              "Your payment is still being checked. Try again to continue to your details.",
            );
            setCanRetryCheckout(true);
          }
        } else {
          setPurchases((previous) =>
            previous.filter((item) => item.sessionId !== sessionId),
          );
          if (data.status !== "refund_pending") forgetCheckout(sessionId);
          if (
            sessionId === returnSession ||
            data.status === "refund_pending" ||
            data.status === "refunded"
          ) {
            setStatus(paymentMessages[data.status] || "Payment checked.");
            if (data.status !== "refund_pending" && sessionId === returnSession)
              history.replaceState({}, "", "/#live-auction");
          }
        }
      } catch {
        if (!cancelled) {
          setStatus(
            "We couldn’t check your payment yet. Try again to continue. You won’t be charged again.",
          );
          setCanRetryCheckout(true);
        }
      }
    };
    // Check each saved payment independently, including a payment whose browser
    // never made it back from Stripe. No new checkout is created by recovery.
    void (async () => {
      for (const sessionId of sessionIds) {
        if (cancelled) break;
        await confirm(sessionId);
      }
    })();
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkoutRetry]);

  function finishPurchase(result: CheckoutConfirmation) {
    accept(result.snapshot);
    if (editingPurchase) {
      const { sessionId } = editingPurchase;
      if (result.status !== "refund_pending") forgetCheckout(sessionId);
      setPurchases((previous) =>
        previous.filter((item) => item.sessionId !== sessionId),
      );
    }
    setEditingPurchase(null);
    setStatus(paymentMessages[result.status] || "Your spot has been saved.");
    history.replaceState({}, "", "/#live-auction");
  }
  const openedEmailSpot = useRef(false);
  useEffect(() => {
    if (!loaded || openedEmailSpot.current) return;
    openedEmailSpot.current = true;
    const url = new URL(location.href);
    const slot = slots.find((s) => s.id === url.searchParams.get("spot"));
    if (slot) {
      const amount = Number(url.searchParams.get("amount"));
      if (Number.isSafeInteger(amount) && amount >= 100 && amount <= 99_999_999)
        setInitialAmount(amount);
      setSelected(slot);
      url.searchParams.delete("spot");
      url.searchParams.delete("amount");
      if (url.searchParams.get("checkout") === "cancelled")
        url.searchParams.delete("checkout");
      history.replaceState({}, "", url.pathname + url.search + "#live-auction");
    }
  }, [loaded, slots]);

  function choose(id: string) {
    setInitialAmount(undefined);
    const slot = slots.find((s) => s.id === id);
    if (slot) {
      setSelected(slot);
      setManualView(slot.face as View);
    }
  }
  return (
    <>
      <a href="#live-auction" className="skip-link">
        Skip to ad spaces
      </a>
      <SiteHeader
        onQuickBuy={loaded && heroSlot ? () => choose(heroSlot.id) : undefined}
      />
      <main>
        <section className="hero">
          <div className="live-indicator">
            <span className="live-status">
              <span className={connected ? "tiny-dot" : "tiny-dot muted"} />
              {snapshot.paymentMode === "test"
                ? "Test drive · no real payments"
                : connected
                  ? "The auction is always live"
                  : loaded
                    ? "Reconnecting live updates"
                    : "Connecting to the garage"}
            </span>
            <span className="audience-counts">
              <span className="muted-separator">·</span>
              <span>
                {connected && snapshot.online > 0
                  ? `${snapshot.online} online now`
                  : `${slots.length} spots. One tiny driver.`}
              </span>
              {snapshot.totalViews != null && (
                <>
                  <span aria-hidden="true">·</span>
                  <span title="Page views recorded by Cloudflare Web Analytics since tracking began; known bots excluded. Updated every five minutes.">
                    {snapshot.totalViews.toLocaleString("en-US")} total views
                  </span>
                </>
              )}
            </span>
          </div>
          <h1>
            Your brand on <span>the fly’s car.</span>
          </h1>
          <p className="hero-description">
            We’re teaching a fly to drive. Your logo can come along for the
            ride.
          </p>
          <div className="hero-cta">
            <button
              type="button"
              className="primary hero-cta-button"
              disabled={!loaded || !heroSlot}
              aria-haspopup="dialog"
              onClick={() => heroSlot && choose(heroSlot.id)}
            >
              Add my logo
              <ArrowUpRight size={19} />
            </button>
            <span className="hero-cta-note">
              {loaded
                ? highestBid
                  ? `Take the top spot from ${highestBid.brand} · ${money(minimumBid(highestBid.amount))} or more`
                  : `${slots.length - taken} of ${slots.length} spots open · from ${money(entryBid)}`
                : "Loading the live auction…"}
            </span>
          </div>
          <div className="hero-stats">
            <div>
              <strong>{loaded ? money(snapshot.totalRaised) : "—"}</strong>
              <span>
                {snapshot.paymentMode === "test"
                  ? "in test payments"
                  : "raised for the experiment"}
              </span>
            </div>
            <span className="stat-divider" />
            <div>
              <button
                type="button"
                className="entry-bid-link"
                disabled={!loaded || !entrySlot}
                aria-haspopup="dialog"
                onClick={() => entrySlot && choose(entrySlot.id)}
              >
                <strong>{loaded ? money(entryBid) : "—"}</strong>
                <span>current minimum to get on the car</span>
              </button>
            </div>
            <span className="stat-divider" />
            <div className="highest-bid-stat">
              <strong>{highestBid ? money(highestBid.amount) : "—"}</strong>
              <span>highest bid</span>
            </div>
          </div>
          <div className="funding-progress">
            <div className="funding-progress-label">
              <span>{money(fundingTarget)} experiment goal</span>
              <strong>
                {loaded
                  ? `${fundingPercent >= 100 ? "Goal reached · " : ""}${fundingLabel}`
                  : "—"}
              </strong>
            </div>
            <div
              className="funding-progress-track"
              role="progressbar"
              aria-label="Experiment funding"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={loaded ? Math.min(100, fundingPercent) : undefined}
              aria-valuetext={
                loaded
                  ? `${money(snapshot.totalRaised)} raised of ${money(fundingTarget)} goal, ${fundingLabel}`
                  : "Loading funding progress"
              }
            >
              <div
                style={{
                  width: `${loaded ? Math.min(100, fundingPercent) : 0}%`,
                }}
              />
            </div>
          </div>
          <div
            className="view-selector"
            aria-label="Car angle"
            aria-describedby="opening-view-note"
          >
            {views.map((option) => (
              <button
                key={option.id}
                aria-pressed={view === option.id}
                onClick={() => setManualView(option.id)}
                className={view === option.id ? "active" : ""}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="opening-view-note" id="opening-view-note">
            {highestBid ? (
              <span
                className="opening-view-leader"
                title="The current highest bid on the car."
              >
                Highest bid · <strong>{highestBid.brand}</strong> ·{" "}
                {money(highestBid.amount)}
              </span>
            ) : (
              <span>
                {loaded
                  ? "Drag to take a closer look."
                  : "Loading the live livery…"}
              </span>
            )}
          </div>
          <div className="hero-car">
            <CarViewer
              placements={snapshot.placements}
              selected={selected?.id || null}
              view={view}
              onSelect={choose}
              autoRotate={manualView === null}
              onInteract={() => setManualView(view)}
              onResetView={() => setManualView("perspective")}
            />
          </div>
          <div className="under-car">
            <span>
              <span className="tiny-dot" />{" "}
              {taken === slots.length
                ? `All ${slots.length} spots are taken. Outbid a sponsor to get on the car.`
                : `${slots.length - taken} spots waiting for their first passenger`}
            </span>
            <a href="#live-auction">
              {taken === slots.length ? "Outbid a sponsor" : "Find your spot"}{" "}
              <ArrowDown size={14} />
            </a>
          </div>
          <aside className="hero-disclaimer" aria-label="Sponsor disclaimer">
            <span className="hero-disclaimer-label">SPONSOR DISCLAIMER</span>
            <p>
              We do not directly endorse any of the sponsors featured here. We
              do not receive any ongoing benefits from any of the featured
              sponsors and are{" "}
              <strong>
                not associated with any cryptocurrencies or coins.
              </strong>
            </p>
            <a className="text-link" href="/media">
              Watch the fly <ArrowDown size={13} />
            </a>
          </aside>
        </section>

        <CustomWrapOffer snapshot={snapshot} loaded={loaded} accept={accept} />

        <section className="auction-section section-wrap" id="live-auction">
          <div className="section-heading">
            <div>
              <div className="eyebrow">
                <span className="tiny-dot" /> NO FINISH LINE
              </div>
              <h2>
                A little space.
                <br className="mobile-only" /> An open-ended race.
              </h2>
              <p>
                Pick a spot, name your price, make it yours. Stay until someone
                pays more.
              </p>
            </div>
            <span className="outline-pill">
              Outbid the current owner by $1 or more
            </span>
          </div>
          {purchases.length > 0 && (
            <div
              className="checkout-resume"
              aria-label="Finish your paid spots"
            >
              <div>
                <strong>Your payment is saved.</strong>
                <p>Add your details when you’re ready to go live.</p>
              </div>
              {purchases.map((purchase) => (
                <button
                  key={purchase.sessionId}
                  className="primary"
                  onClick={() => {
                    setSelected(null);
                    setEditingPurchase(purchase);
                  }}
                >
                  Finish spot {purchase.slotId.slice(3)}{" "}
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
          )}
          {canRetryCheckout && (
            <button
              className="secondary"
              onClick={() => setCheckoutRetry((value) => value + 1)}
            >
              Check payment again
            </button>
          )}
          {status && (
            <div className="payment-status" role="status">
              <Check size={19} />
              <span>{status}</span>
              <button
                aria-label="Dismiss payment update"
                onClick={() => setStatus("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!loaded && (
            <p className="connection-notice" role="status">
              Connecting to live prices. Checkout will be available after the
              latest auction state loads.
            </p>
          )}
          <div className="auction-toolbar">
            <div className="spot-filters" aria-label="Filter spots">
              {[
                { id: "all", label: "All spots" },
                { id: "available", label: "Unclaimed" },
                ...views
                  .filter((v) => v.id !== "perspective")
                  .map((v) => ({ id: v.id, label: v.label })),
              ].map((item) => (
                <button
                  key={item.id}
                  className={filter === item.id ? "active" : ""}
                  aria-pressed={filter === item.id}
                  onClick={() => {
                    setFilter(item.id);
                    if (item.id !== "all" && item.id !== "available")
                      setManualView(item.id as View);
                  }}
                >
                  {item.label}
                  {item.id === "all" && <span>{slots.length}</span>}
                </button>
              ))}
            </div>
            <div className="search-spots">
              <Search size={15} />
              <input
                aria-label="Search spots"
                placeholder="Find a spot…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          </div>
          <div className="table-container">
            <table className="spots-table">
              <thead>
                <tr>
                  <th>Riding with us</th>
                  <th className="location-cell">On the car</th>
                  <th>
                    <button
                      className="sort-button"
                      onClick={() =>
                        setSort(sort === "price" ? "number" : "price")
                      }
                    >
                      Current bid <ChevronDown size={13} />
                    </button>
                  </th>
                  <th>
                    <span className="sr-only">Claim spot</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {displayed.map((slot) => {
                  const placement = snapshot.placements[slot.id];
                  return (
                    <tr key={slot.id}>
                      <td>
                        {placement ? (
                          <a
                            className="advertiser-profile"
                            href={placement.url}
                            target="_blank"
                            rel="noopener noreferrer sponsored"
                          >
                            <span className="advertiser-logo">
                              <img src={placement.logoUrl} alt="" />
                            </span>
                            <span className="advertiser-copy">
                              <strong>{placement.brand}</strong>
                              {placement.message && (
                                <span className="advertiser-message">
                                  {placement.message}
                                </span>
                              )}
                              <span
                                className="advertiser-url"
                                title={placement.url}
                              >
                                <span>
                                  {placement.url
                                    .replace(/^https:\/\/(www\.)?/, "")
                                    .replace(/\/$/, "")}
                                </span>
                                <ArrowUpRight size={15} />
                              </span>
                            </span>
                          </a>
                        ) : (
                          <button
                            className="advertiser-profile open-profile"
                            onClick={() => choose(slot.id)}
                            disabled={!loaded}
                          >
                            <span
                              className="advertiser-logo open-logo"
                              aria-hidden="true"
                            >
                              +
                            </span>
                            <span className="advertiser-copy">
                              <strong>Your brand could be here</strong>
                              <span className="available-label">
                                Your logo, message, and a link to your world.
                              </span>
                            </span>
                          </button>
                        )}
                      </td>
                      <td className="location-cell">
                        <button
                          className="spot-title"
                          onClick={() => choose(slot.id)}
                          aria-label={`View ${slot.name}`}
                        >
                          <span>
                            {slot.name}
                            <small>
                              {Math.round(slot.width_m * 100)} ×{" "}
                              {Math.round(slot.height_m * 100)} cm
                            </small>
                          </span>
                        </button>
                      </td>
                      <td className="price-cell">
                        {placement ? (
                          money(placement.amount)
                        ) : (
                          <>
                            <span>from </span>$1
                          </>
                        )}
                      </td>
                      <td>
                        <button
                          className="primary claim-button"
                          onClick={() => choose(slot.id)}
                          disabled={!loaded}
                        >
                          {placement ? "Outbid" : "Claim spot"}
                          <ArrowUpRight size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!filtered.length && (
              <div className="empty-search">
                No spots match that search. Try a different side or name.
              </div>
            )}
          </div>
          <div className="table-footer">
            <span>
              Showing {displayed.length} of {filtered.length} spots
            </span>
            {filter === "all" && !query && (
              <button onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show fewer spots" : `See all ${slots.length} spots`}
                <ChevronDown
                  size={15}
                  style={{ transform: showAll ? "rotate(180deg)" : undefined }}
                />
              </button>
            )}
            <span>USD · One-time payments</span>
          </div>
        </section>

        <HistoricalBids
          bids={snapshot.highestBids}
          placements={snapshot.placements}
          loaded={loaded}
        />

        <section className="how-section section-wrap" id="how-it-works">
          <div className="eyebrow">THE RULES OF THE ROAD</div>
          <h2>Pretty simple. Unlike teaching a fly to drive.</h2>
          <div className="how-steps">
            {[
              [
                "01",
                "Find your favorite spot.",
                "Spin the Mini. Browse the seven large placements on the doors, windows, bonnet, roof, and front grille.",
              ],
              [
                "02",
                "Put your money where your logo is.",
                "Choose a bid at least $1 above the current owner, then pay once through Stripe. You’ll add your brand and artwork when you return.",
              ],
              [
                "03",
                "Add your details. Take your spot.",
                "Add your brand, website, and artwork. Preview it on the car, then publish. Your ad stays until a higher paid bid publishes its artwork.",
              ],
            ].map(([number, title, body]) => (
              <div key={number}>
                <span className="step-number">{number}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section
          className="experiment-section section-wrap"
          id="the-experiment"
        >
          <div className="experiment-art">
            <FlyMark size={150} />
            <span className="orbit-label label-top">165,122 neurons</span>
            <span className="orbit-label label-bottom">
              1 very ambitious fly
            </span>
            <div className="orbit-ring ring-one" />
            <div className="orbit-ring ring-two" />
          </div>
          <div className="experiment-copy">
            <div className="eyebrow">WHY ON EARTH?</div>
            <h2>
              A tiny brain.
              <br />A very big road ahead.
            </h2>
            <p>
              I’m Mark. I’m building an experiment to see whether a neural model
              based on a real fruit fly’s brain can learn to drive a simulated
              car.
            </p>
            <p>
              Its legs already turn a physical steering wheel in simulation.
              There’s still a long way to go. Your ad helps fund the compute and
              the next experiments—and gives this little Mini some personality.
            </p>
            <a href="#faq" className="text-link">
              More about the experiment <ArrowUpRight size={16} />
            </a>
            <div className="research-note">
              A simulated fly, a measured connectome, and a real research
              question. No living flies are behind the wheel.
            </div>
          </div>
        </section>

        <MediaSection />

        <section className="faq-section section-wrap" id="faq">
          <div>
            <div className="eyebrow">FAIR QUESTIONS</div>
            <h2>
              A few things
              <br />
              before we set off.
            </h2>
          </div>
          <div className="faq-items">
            {faqs.map(([question, answer]) => (
              <details key={question}>
                <summary>
                  {question}
                  <span>+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="final-cta">
          <FlyMark size={40} />
          <h2>Hop on. The fly’s driving.</h2>
          <p>Your next questionable marketing decision is one bid away.</p>
          <a href="#live-auction" className="primary">
            Find your spot <ArrowUpRight size={17} />
          </a>
        </section>
      </main>
      <SiteFooter />
      {editingPurchase &&
        allSlots.some((slot) => slot.id === editingPurchase.slotId) && (
          <BidDialog
            key={editingPurchase.sessionId}
            slot={allSlots.find((slot) => slot.id === editingPurchase.slotId)!}
            snapshot={snapshot}
            purchase={editingPurchase}
            onComplete={finishPurchase}
            onClose={() => setEditingPurchase(null)}
          />
        )}
      {selected && !editingPurchase && (
        <BidDialog
          key={selected.id}
          slot={selected}
          snapshot={snapshot}
          initialAmount={initialAmount}
          onComplete={finishPurchase}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
