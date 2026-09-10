"use client";

import { useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import { money, type Placement } from "@/lib/auction";
import styles from "./historical-bids.module.css";

export default function HistoricalBids({
  bids,
  placements,
  loaded,
}: {
  bids: Placement[];
  placements: Record<string, Placement>;
  loaded: boolean;
}) {
  const [page, setPage] = useState(0);
  const pageSize = 8;
  const pageCount = Math.ceil(bids.length / pageSize);
  const currentPage = Math.min(page, Math.max(0, pageCount - 1));
  const start = currentPage * pageSize;
  const displayed = bids.slice(start, start + pageSize);
  const currentIds = new Set(Object.values(placements).map((bid) => bid.id));

  return (
    <section
      className={`section-wrap ${styles.section}`}
      id="leaderboard"
      aria-labelledby="highest-bids-title"
    >
      <div className="eyebrow">THE PASSENGER SEAT</div>
      <h2 id="highest-bids-title">Highest bids, past and present.</h2>
      <p>
        Big love for everyone helping the little fly. Past sponsors keep their
        place in the history, with a link to their world.
      </p>
      {bids.length ? (
        <>
          <table className={styles.table}>
            <caption className="sr-only">
              The 50 highest paid bids of all time, highest first. Amounts in US
              dollars, excluding complimentary credits.
            </caption>
            <thead>
              <tr>
                <th scope="col" className={styles.rank}>
                  <span className="sr-only">Rank</span>#
                </th>
                <th scope="col">Supporter</th>
                <th scope="col" className={styles.amount}>
                  Paid bid
                </th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((bid, index) => (
                <tr key={bid.id}>
                  <td className={styles.rank}>
                    {String(start + index + 1).padStart(2, "0")}
                  </td>
                  <td>
                    <a
                      className={styles.supporter}
                      href={bid.url}
                      title={bid.url}
                      target="_blank"
                      rel="noopener noreferrer sponsored"
                    >
                      <strong>{bid.brand}</strong>
                      <ArrowUpRight size={14} aria-hidden="true" />
                    </a>
                    <div className={styles.detail}>
                      <time dateTime={new Date(bid.publishedAt).toISOString()}>
                        {new Date(bid.publishedAt).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                          timeZone: "UTC",
                        })}
                      </time>
                      <span aria-hidden="true"> · </span>
                      <span>
                        {currentIds.has(bid.id) ? "On the car" : "Past sponsor"}
                      </span>
                    </div>
                  </td>
                  <td className={styles.amount}>
                    <strong>{money(bid.amount)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className={styles.footer}>
            <span aria-live="polite">
              {start + 1}–{start + displayed.length} of {bids.length} bids · USD
            </span>
            {pageCount > 1 && (
              <nav className={styles.pagination} aria-label="Leaderboard pages">
                <button
                  type="button"
                  aria-label="Previous bids"
                  disabled={currentPage === 0}
                  onClick={() => setPage(currentPage - 1)}
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                  Previous
                </button>
                <span>
                  Page {currentPage + 1} of {pageCount}
                </span>
                <button
                  type="button"
                  aria-label="Next bids"
                  disabled={currentPage === pageCount - 1}
                  onClick={() => setPage(currentPage + 1)}
                >
                  Next
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </nav>
            )}
          </div>
        </>
      ) : (
        <div className={styles.empty}>
          {loaded ? (
            <>
              <p>The first paid bid starts the story.</p>
              <a href="#live-auction">
                Be the first on board <ArrowUpRight size={15} />
              </a>
            </>
          ) : (
            <p role="status">Loading bid history…</p>
          )}
        </div>
      )}
    </section>
  );
}
