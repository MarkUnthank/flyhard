import { ArrowUpRight } from "lucide-react";
import FlyMark from "./fly-mark";

export default function SiteHeader({
  currentPage = "home",
}: {
  currentPage?: "home" | "media";
}) {
  const home = currentPage === "home" ? "" : "/";
  return (
    <header className="site-header">
      <a className="wordmark" href="/">
        <FlyMark size={31} />
        <span>
          The Driving Fly<span className="wordmark-period">.</span>
        </span>
      </a>
      <nav aria-label="Main navigation">
        <a href={`${home}#live-auction`}>Live auction</a>
        <a href={`${home}#custom-wrap`}>Custom wrap</a>
        <a href={`${home}#leaderboard`}>Supporters</a>
        <a href={`${home}#how-it-works`}>How it works</a>
        <a
          href="/media"
          aria-current={currentPage === "media" ? "page" : undefined}
        >
          Videos &amp; data
        </a>
        <a href={`${home}#the-experiment`}>The experiment</a>
      </nav>
      <a className="primary header-cta" href={`${home}#live-auction`}>
        Get a spot <ArrowUpRight size={16} />
      </a>
    </header>
  );
}
