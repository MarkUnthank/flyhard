import { ArrowUpRight } from "lucide-react";

export default function MediaSection() {
  return (
    <section
      className="media-teaser section-wrap"
      aria-labelledby="media-teaser-title"
    >
      <div>
        <div className="eyebrow">FROM THE LAB</div>
        <h2 id="media-teaser-title">Six legs. See for yourself.</h2>
        <p>The films, the experiments, and the data behind the tiny driver.</p>
      </div>
      <a href="/media" className="primary">
        Watch the films <ArrowUpRight size={17} />
      </a>
    </section>
  );
}
