import type { Metadata } from "next";
import { ArrowDownToLine, ArrowUpRight } from "lucide-react";
import FlyMark from "@/components/fly-mark";
import SiteHeader from "@/components/site-header";
import SiteFooter from "@/components/site-footer";
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
        url: "/media/three-point-turn.jpg",
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
    images: ["/media/three-point-turn.jpg"],
  },
};

export default function MediaPage() {
  return (
    <>
      <a href="#recordings" className="skip-link">
        Skip to recordings
      </a>
      <SiteHeader currentPage="media" />
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
          <a className="journal-press-link" href="/press">
            Covering the story? Get the press kit <ArrowUpRight size={16} />
          </a>
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
                    {entry.category} · {entry.duration} · {entry.audio} ·{" "}
                    {entry.playback}
                  </span>
                  <a href={`#${entry.id}`}>
                    Link to this film <ArrowUpRight size={13} />
                  </a>
                </figcaption>
              </figure>
              {entry.stills && (
                <div
                  className="journal-stills"
                  aria-label={`Stills from ${entry.title}`}
                >
                  {entry.stills.map((still) => (
                    <figure key={still.file}>
                      <a
                        href={`/media/${still.file}`}
                        download
                        aria-label={`Download: ${still.caption}`}
                      >
                        <img
                          src={`/media/${still.file}`}
                          alt={still.caption}
                          width={1920}
                          height={1080}
                          loading="lazy"
                        />
                      </a>
                      <figcaption>
                        {still.caption}
                        <a href={`/media/${still.file}`} download>
                          Download still <ArrowDownToLine size={13} />
                        </a>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              )}
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
                    {entry.evidenceLink ?? "Explore the data on GitHub"}{" "}
                    <ArrowUpRight size={16} />
                    <small>{entry.evidenceLabel}</small>
                  </a>
                  <div className="journal-downloads">
                    <a href={`/media/${entry.id}.mp4`} download>
                      <ArrowDownToLine size={15} /> Download video
                    </a>
                    <a href={`/media/${entry.id}.jpg`} download>
                      <ArrowDownToLine size={15} /> Download screenshot
                    </a>
                    {entry.downloads?.map((download) => (
                      <a key={download.file} href={download.file} download>
                        <ArrowDownToLine size={15} /> {download.label}
                      </a>
                    ))}
                  </div>
                </aside>
              </div>
            </article>
          ))}
        </div>
      </main>
      <section className="final-cta" aria-labelledby="media-sponsor-title">
        <FlyMark size={40} />
        <h2 id="media-sponsor-title">Help the fly go further.</h2>
        <p>Put your brand on the Mini and help fund the next experiment.</p>
        <a href="/#live-auction" className="primary">
          Get a spot on the car <ArrowUpRight size={17} />
        </a>
      </section>
      <SiteFooter />
    </>
  );
}
