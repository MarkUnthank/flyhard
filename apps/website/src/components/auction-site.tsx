"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Search,
  Trophy,
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
} from "@/lib/auction";
import { useAuction } from "./use-auction";
import FlyMark from "./fly-mark";
import BidDialog from "./bid-dialog";
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
    "Their artwork replaces yours when their payment is confirmed. Your brand remains in the recent supporter history. A placement that has already gone live isn’t refunded just because it is outbid.",
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
    "A logo, project, or original design you have permission to use. Upload a PNG, JPG, or WebP, choose its background, and check the preview before paying. Illegal, hateful, explicit, misleading, or infringing ads can be removed under the placement terms.",
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
  const [sort, setSort] = useState("number");
  const [showAll, setShowAll] = useState(false);
  const slots = useMemo(
    () => activeSlots(snapshot.placements),
    [snapshot.placements],
  );
  const taken = Object.keys(snapshot.placements).length;
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
    [filter, query, sort, snapshot.placements, slots],
  );
  const displayed =
    showAll || filter !== "all" || query ? filtered : filtered.slice(0, 12);
  const leaders = rankPlacements(snapshot.placements).slice(0, 5);
  const highestBid = leaders[0];
  const leadingSlot = slots.find((slot) => slot.id === highestBid?.slotId);
  const openingView: View = (leadingSlot?.face as View) ?? "perspective";
  const view = manualView ?? openingView;
  const openingLabel = views.find((option) => option.id === openingView)!.label;

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("checkout") === "cancelled") {
      setStatus("Checkout cancelled. Your card has not been charged.");
      return;
    }
    const sessionId = params.get("session_id");
    if (!sessionId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const confirm = async () => {
      setStatus(
        "Checking your payment. Your artwork will appear as soon as it’s confirmed…",
      );
      try {
        const response = await fetch("/api/checkout/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId }),
        });
        const data = (await response.json()) as {
          error?: string;
          status: string;
          snapshot: AuctionSnapshot;
        };
        if (cancelled) return;
        if (!response.ok) throw new Error(data.error);
        accept(data.snapshot);
        const messages: Record<string, string> = {
          won: "You’re on the car. Your payment is confirmed and your artwork is live.",
          outbid:
            "Your artwork went live, and another supporter has since outbid you. Thank you for being part of the experiment.",
          refund_pending:
            "Someone beat your bid before your ad went live. A full refund has been requested.",
          refunded:
            "Someone beat your bid before your ad went live. Your payment has been refunded.",
          expired:
            "This checkout has expired. You can start a new bid whenever you’re ready.",
        };
        if (messages[data.status]) {
          setStatus(messages[data.status]);
          history.replaceState({}, "", "/#live-auction");
        } else if (++attempts < 20) timer = setTimeout(confirm, 3000);
        else
          setStatus(
            "Your payment is still being checked. You can close this page; confirmed payments publish automatically.",
          );
      } catch {
        if (!cancelled)
          setStatus(
            "We couldn’t check the payment yet. Keep your checkout receipt; confirmed payments are processed automatically.",
          );
      }
    };
    void confirm();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // The return URL only asks the server to check payment; it never grants a spot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  function choose(id: string) {
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
      <header className="site-header">
        <a className="wordmark" href="/">
          <FlyMark size={31} />
          <span>
            The Driving Fly<span className="wordmark-period">.</span>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#live-auction">Live auction</a>
          <a href="#leaderboard">Supporters</a>
          <a href="#how-it-works">How it works</a>
          <a href="#the-experiment">The experiment</a>
        </nav>
        <a className="primary header-cta" href="#live-auction">
          Get a spot <ArrowUpRight size={16} />
        </a>
      </header>
      <main>
        <section className="hero">
          <div className="live-indicator">
            <span className={connected ? "tiny-dot" : "tiny-dot muted"} />
            {snapshot.paymentMode === "test"
              ? "Test drive · no real payments"
              : connected
                ? "The auction is always live"
                : loaded
                  ? "Reconnecting live updates"
                  : "Connecting to the garage"}
            <span className="muted-separator">·</span>
            <span>
              {connected && snapshot.online > 0
                ? `${snapshot.online} online now`
                : `${slots.length} spots. One tiny driver.`}
            </span>
          </div>
          <h1>
            Your brand. A car. <span>A fly.</span>
          </h1>
          <p className="hero-description">
            We’re teaching a fly to drive. Your logo can come along for the
            ride.
          </p>
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
              <strong>
                {loaded ? taken : "—"}
                <span className="stat-denominator"> / {slots.length}</span>
              </strong>
              <span>spots claimed</span>
            </div>
            <span className="stat-divider" />
            <div>
              <strong>$1</strong>
              <span>to get on the car</span>
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
            <span>
              <Trophy size={14} /> Highest bid gets the first look.
            </span>
            {highestBid ? (
              <span
                className="opening-view-leader"
                title="The opening angle follows the highest current placement. Equal bids favor the earlier purchase. Reset returns to this side."
              >
                Opens on {openingLabel.toLowerCase()} ·{" "}
                <strong>{highestBid.brand}</strong> · {money(highestBid.amount)}
              </span>
            ) : (
              <span>
                {loaded
                  ? "The first bid will set the opening angle."
                  : "Finding the highest bid…"}
              </span>
            )}
          </div>
          <div className="hero-car">
            <CarViewer
              placements={snapshot.placements}
              selected={selected?.id || null}
              view={view}
              onSelect={choose}
              resetView={openingView}
              onInteract={() => setManualView(view)}
              onResetView={() => setManualView(null)}
            />
          </div>
          <div className="under-car">
            <span>
              <span className="tiny-dot" /> {slots.length - taken} spots waiting
              for their first passenger
            </span>
            <a href="#live-auction">
              Find your spot <ArrowDown size={14} />
            </a>
          </div>
          <p className="hero-footnote">
            Six legs. One steering wheel. A questionable business model.
          </p>
        </section>

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
            <span className="outline-pill">Every empty spot starts at $1</span>
          </div>
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
                          aria-label={`View spot ${slot.id.slice(3)}: ${slot.name}`}
                        >
                          <span
                            className="spot-swatch"
                            style={
                              {
                                "--spot-color": slot.color,
                              } as React.CSSProperties
                            }
                          >
                            {slot.id.slice(3)}
                          </span>
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
                          className="claim-button"
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

        <section className="supporter-section section-wrap" id="leaderboard">
          <div className="supporter-column">
            <div className="eyebrow">THE PASSENGER SEAT</div>
            <h2>Big love for the little fly.</h2>
            <p>The brands helping this experiment get somewhere.</p>
            {leaders.length ? (
              <ol className="leader-list">
                {leaders.map((placement, index) => (
                  <li key={placement.id}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <img src={placement.logoUrl} alt="" />
                    <a
                      href={placement.url}
                      target="_blank"
                      rel="noopener noreferrer sponsored"
                    >
                      {placement.brand}
                      <ArrowUpRight size={13} />
                    </a>
                    <strong>{money(placement.amount)}</strong>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="empty-leaders">
                <div className="empty-podium">
                  <span>02</span>
                  <span>
                    <FlyMark size={28} />
                    01
                  </span>
                  <span>03</span>
                </div>
                <strong>A small car. Room for the first big believer.</strong>
                <a href="#live-auction">
                  Be the first on board <ArrowRight size={15} />
                </a>
              </div>
            )}
          </div>
          <div className="activity-column">
            <div className="activity-title">
              <h3>Fresh tire tracks</h3>
              <span className="live-tag">
                <span className={connected ? "tiny-dot" : "tiny-dot muted"} />
                {connected ? "Live" : "Reconnecting"}
              </span>
            </div>
            {snapshot.history.length ? (
              <ul className="activity-list">
                {snapshot.history.slice(0, 6).map((placement) => (
                  <li key={placement.id}>
                    <span className="activity-dot" />
                    <div>
                      <a
                        href={placement.url}
                        target="_blank"
                        rel="noopener noreferrer sponsored"
                      >
                        {placement.brand}
                      </a>{" "}
                      claimed{" "}
                      <strong>
                        {slots.find((s) => s.id === placement.slotId)?.name}
                      </strong>
                      <small>
                        {new Date(placement.publishedAt).toLocaleDateString(
                          "en-US",
                          { month: "short", day: "numeric" },
                        )}{" "}
                        · {money(placement.amount)}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="empty-activity">
                <span className="activity-line" />
                <p>
                  No tire tracks just yet.
                  <br />
                  <span>The first claim starts the story.</span>
                </p>
              </div>
            )}
            <div className="activity-footer">
              {snapshot.totalPurchases} paid placements and counting
              <ArrowUpRight size={15} />
            </div>
          </div>
        </section>

        <section className="how-section section-wrap" id="how-it-works">
          <div className="eyebrow">THE RULES OF THE ROAD</div>
          <h2>Pretty simple. Unlike teaching a fly to drive.</h2>
          <div className="how-steps">
            {[
              [
                "01",
                "Find your favorite spot.",
                "Spin the Mini. Browse the doors, roof, bonnet, bumpers, and even the mirrors. Every empty spot starts at just $1.",
              ],
              [
                "02",
                "Put your money where your logo is.",
                "Upload your artwork. Start at $1, or bid at least $1 above the current owner. Pay once through Stripe. That’s your whole commitment.",
              ],
              [
                "03",
                "Ride until you’re outbid.",
                "Your artwork goes live automatically after payment. It stays until someone pays more. No countdown. The auction never parks.",
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
          <p>Your next questionable marketing decision starts at $1.</p>
          <a href="#live-auction" className="primary">
            Find your spot <ArrowUpRight size={17} />
          </a>
        </section>
      </main>
      <footer className="site-footer">
        <div>
          <a className="wordmark" href="/">
            <FlyMark size={25} />
            <span>The Driving Fly.</span>
          </a>
          <p className="company-credit">
            A{" "}
            <a
              href="https://reallynice.company"
              target="_blank"
              rel="noopener noreferrer"
            >
              Really Nice
            </a>{" "}
            project.
          </p>
        </div>
        <div className="footer-links">
          <a
            className="footer-social"
            href="https://x.com/alright_mark"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="@alright_mark on X"
          >
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.64 7.584H.47l8.6-9.835L0 1.154h7.594l5.243 6.932 6.064-6.933Zm-1.29 19.49h2.039L6.487 3.24H4.3l13.31 17.403Z" />
            </svg>
            @alright_mark
          </a>
          <a href="/terms">Placement terms</a>
          <a href="/privacy">Privacy</a>
          <a href="/credits">Credits</a>
        </div>
        <p className="footer-disclaimer">
          Vehicle model adapted from CARLA 0.9.16 (CVC, Universitat Autònoma de
          Barcelona), CC BY. The Driving Fly is an independent project.
        </p>
      </footer>
      {selected && (
        <BidDialog
          key={selected.id}
          slot={selected}
          snapshot={snapshot}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
