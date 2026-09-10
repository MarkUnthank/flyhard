import type { Metadata } from "next";
import { ArrowDownToLine, ArrowLeft, ArrowUpRight } from "lucide-react";
import FlyMark from "@/components/fly-mark";
import { mediaEntries } from "@/lib/media";

export const metadata: Metadata = {
  title: "From the lab — The Driving Fly",
  description:
    "Follow the fly’s progress through experiment films, screenshots, and open run data. Small steps towards teaching a simulated fly to drive.",
  alternates: { canonical: "/media" },
  openGraph: {
    title: "From the lab — The Driving Fly",
    description:
      "The films, the experiments, and the data behind the tiny driver.",
    url: "/media",
    images: [
      {
        url: "/media/calm-steering.jpg",
        width: 1920,
        height: 1080,
        alt: "The simulated fly, its neural activity, and the car it steers",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "From the lab — The Driving Fly",
    description:
      "The films, the experiments, and the data behind the tiny driver.",
    images: ["/media/calm-steering.jpg"],
  },
};

export default function MediaPage() {
  return (
    <>
      <a href="#recordings" className="skip-link">
        Skip to recordings
      </a>
      <header className="site-header journal-header">
        <a className="wordmark" href="/">
          <FlyMark size={31} />
          <span>
            The Driving Fly<span className="wordmark-period">.</span>
          </span>
        </a>
        <a className="text-link" href="/">
          Back to the car <ArrowUpRight size={16} />
        </a>
      </header>
      <main className="media-journal">
        <header className="journal-intro">
          <div className="eyebrow">THE DRIVING FLY / FIELD NOTES</div>
          <h1>
            A tiny driver.
            <br />
            <span>A story in motion.</span>
          </h1>
          <p>
            The films, the experiments, and the occasional collision. Follow the
            fly’s progress, and look under the bonnet at the data behind it.
          </p>
          <nav className="journal-index" aria-label="Recordings">
            {mediaEntries.map((entry) => (
              <a key={entry.id} href={`#${entry.id}`}>
                <span>{entry.number}</span>
                {entry.title}
                <span aria-hidden="true">↓</span>
              </a>
            ))}
          </nav>
        </header>
        <div id="recordings">
          {mediaEntries.map((entry) => (
            <article
              className="journal-entry"
              id={entry.id}
              key={entry.id}
              aria-labelledby={`${entry.id}-title`}
            >
              <header className="journal-entry-heading">
                <div className="eyebrow">
                  FILM {entry.number} <span aria-hidden="true">/</span>{" "}
                  <time dateTime={entry.date}>{entry.dateLabel}</time>
                </div>
                <h2 id={`${entry.id}-title`}>
                  <a href={`#${entry.id}`}>{entry.title}</a>
                </h2>
                <p>{entry.intro}</p>
              </header>
              <figure className="journal-film">
                <video
                  controls
                  playsInline
                  preload="none"
                  poster={`/media/${entry.id}.jpg`}
                  aria-label={entry.title}
                  aria-describedby={`${entry.id}-caption`}
                >
                  <source src={`/media/${entry.id}.mp4`} type="video/mp4" />
                  <a href={`/media/${entry.id}.mp4`}>Download this recording</a>
                </video>
                <figcaption id={`${entry.id}-caption`}>
                  <span>
                    {entry.category} · {entry.duration} · Silent · Normal
                    simulation speed
                  </span>
                  <a href={`#${entry.id}`}>
                    Link to this film <ArrowUpRight size={13} />
                  </a>
                </figcaption>
              </figure>
              <div className="journal-story">
                <div className="journal-prose">
                  {entry.paragraphs.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                </div>
                <aside
                  className="journal-notebook"
                  aria-label={`Supporting material for ${entry.title}`}
                >
                  <div className="eyebrow">IN THE NOTEBOOK</div>
                  <ul>
                    {entry.facts.map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                  <a
                    className="journal-evidence"
                    href={entry.evidenceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Explore the data on GitHub <ArrowUpRight size={16} />
                    <small>{entry.evidenceLabel}</small>
                  </a>
                  <div className="journal-downloads">
                    <a href={`/media/${entry.id}.mp4`} download>
                      <ArrowDownToLine size={15} /> Download video
                    </a>
                    <a href={`/media/${entry.id}.jpg`} download>
                      <ArrowDownToLine size={15} /> Download screenshot
                    </a>
                  </div>
                </aside>
              </div>
            </article>
          ))}
        </div>
      </main>
      <footer className="journal-footer">
        <a href="/" className="text-link">
          <ArrowLeft size={16} /> Back to the car
        </a>
        <span>Six legs. One experiment. More to come.</span>
        <a href="/credits">Credits</a>
      </footer>
    </>
  );
}
