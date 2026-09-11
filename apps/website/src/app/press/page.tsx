import type { Metadata } from "next";
import { ArrowDownToLine, ArrowUpRight, Mail, Play } from "lucide-react";
import SiteHeader from "@/components/site-header";
import SiteFooter from "@/components/site-footer";
import FlyMark from "@/components/fly-mark";
import { mediaEntries } from "@/lib/media";
import kit from "@/lib/press-kit.json";
import styles from "./press.module.css";

export const metadata: Metadata = {
  title: "Press kit — The Driving Fly",
  description:
    "The story, films, downloadable screenshots, logos, results and press contact for The Driving Fly, an independent experiment by Mark Unthank.",
  alternates: { canonical: "/press" },
  openGraph: {
    title: "Press kit — The Driving Fly",
    description: kit.summary,
    url: "/press",
    images: [
      {
        url: "/media/three-point-turn.jpg",
        width: 1920,
        height: 1080,
        alt: "The simulated Mini, fly body and neural model during a three-point turn",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Press kit — The Driving Fly",
    description: kit.summary,
    images: ["/media/three-point-turn.jpg"],
  },
};

export default function PressPage() {
  return (
    <>
      <a href="#press-content" className="skip-link">
        Skip to press kit
      </a>
      <SiteHeader currentPage="press" />
      <main id="press-content" className={styles.page}>
        <header className={styles.hero}>
          <div className="eyebrow">THE DRIVING FLY / PRESS KIT</div>
          <div className={styles.heroRow}>
            <h1>
              A very small driver.
              <br />
              <span>A rather good story.</span>
            </h1>
            <p>
              Films, facts and a fly at the wheel.
              <br />
              Everything you need to cover the experiment.
            </p>
          </div>
          <div className={styles.actions}>
            <a
              className="primary"
              href="/press/the-driving-fly-press-kit.zip"
              download
            >
              <ArrowDownToLine size={17} /> Download press kit
            </a>
            <a href={`mailto:${kit.contact}`}>
              <Mail size={17} /> Contact Mark
            </a>
            <span>
              Stills, logos, notes & data · Updated{" "}
              <time dateTime={kit.date}>{kit.updated}</time>
            </span>
          </div>
          <figure className={styles.heroImage}>
            <a
              href="/media#three-point-turn"
              aria-label="Watch the complete three-point turn"
            >
              <img
                src="/media/three-point-turn.jpg"
                width={1920}
                height={1080}
                alt="A green Mini reverses across a marked road, with the fly body and computed neural activity shown alongside."
                fetchPriority="high"
              />
              <span className={styles.watch}>
                <Play size={15} /> Watch the complete turn <span>22.8 sec</span>
              </span>
            </a>
            <figcaption>
              A complete recorded attempt. A simulated car, a simulated body,
              and a model built from measured connections.
            </figcaption>
          </figure>
        </header>

        <section className={styles.story} aria-labelledby="story-title">
          <div>
            <div className="eyebrow">THE STORY</div>
            <h2 id="story-title">
              Teaching a fly to drive.
              <br />
              One small skill at a time.
            </h2>
            <p className={styles.lead}>{kit.summary}</p>
            <p>{kit.boilerplate}</p>
            <a
              className={styles.textLink}
              href="/press/press-notes.txt"
              download
            >
              Download project background & facts <ArrowDownToLine size={15} />
            </a>
          </div>
          <dl className={styles.facts}>
            {kit.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={styles.section} aria-labelledby="results-title">
          <div className={styles.sectionHeading}>
            <div>
              <div className="eyebrow">FOR ACCURATE COVERAGE</div>
              <h2 id="results-title">What the experiments show.</h2>
            </div>
            <a className={styles.textLink} href="/media">
              Read the field notes <ArrowUpRight size={16} />
            </a>
          </div>
          <div className={styles.results}>
            <article>
              <span className={styles.resultNumber}>6 / 8</span>
              <h3>Three-point turns passed</h3>
              <p>
                All eight held-out cases turned without contact or boundary
                crossings. Two missed the stopping-position target. The featured
                film is a separate successful validation take.
              </p>
              <a href="/press/data/three-point-turn-results.json" download>
                Download results <ArrowDownToLine size={14} />
              </a>
            </article>
            <article>
              <span className={styles.resultNumber}>0 / 50</span>
              <h3>Successful parks</h3>
              <p>
                The parking benchmark remains unpassed. Ten learned-core trials
                had collision flags, including virtual-curb or vehicle-bound
                overlap. Every trial is retained in the data.
              </p>
              <a href="/press/data/parking-trials.csv" download>
                Download trial data <ArrowDownToLine size={14} />
              </a>
            </article>
            <article>
              <span className={styles.resultNumber}>One honk.</span>
              <h3>And a few imperfections</h3>
              <p>
                The fly presses a physical horn button. The dynamic film keeps a
                false empty-road chirp; the road-rage film keeps its collision.
                Traffic, route and speed are directed.
              </p>
              <a href="/press/data/horn-notes.md" download>
                Download horn notes <ArrowDownToLine size={14} />
              </a>
            </article>
          </div>
          <div className={styles.context}>
            <h3>A model of connections, with engineered help.</h3>
            <p>
              The model retains 165,122 traced neurons from MaleCNS; this
              filtered set differs from the published full census. Its dynamics,
              sensory mapping and motor assistance are engineered. Current tasks
              use structured geometry or scripted requests, not camera-based
              perception. Neural colours show computed model states. These films
              demonstrate scoped simulated control skills, not a recreated fly
              mind or general autonomous driving.
            </p>
            <p>
              Most body and road views share a recorded clock. In the parking
              montage, the side-panel fly is an explicitly labelled independent
              replay. Sponsor graphics and the cabin fly are composited; the
              footage does not establish a completed native Unreal vehicle
              import.
            </p>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="films-title">
          <div className={styles.sectionHeading}>
            <div>
              <div className="eyebrow">READY TO WATCH & DOWNLOAD</div>
              <h2 id="films-title">The latest films.</h2>
            </div>
            <p>1080p MP4s. Videos download separately from the kit.</p>
          </div>
          <div className={styles.films}>
            {mediaEntries.slice(0, 5).map((film) => (
              <article key={film.id}>
                <a
                  className={styles.filmPreview}
                  href={`/media#${film.id}`}
                  aria-label={`Watch: ${film.title}`}
                >
                  <img
                    src={`/media/${film.id}.jpg`}
                    alt={film.intro}
                    width={1920}
                    height={1080}
                    loading="lazy"
                  />
                  <span>
                    <Play size={14} /> {film.duration}
                  </span>
                </a>
                <div>
                  <span className="eyebrow">{film.category}</span>
                  <h3>
                    <a href={`/media#${film.id}`}>{film.title}</a>
                  </h3>
                  <p>
                    {film.audio} · {film.playback}
                  </p>
                  <a
                    className={styles.textLink}
                    href={`/media/${film.id}.mp4`}
                    download
                  >
                    Download film <ArrowDownToLine size={15} />
                  </a>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section} aria-labelledby="stills-title">
          <div className={styles.sectionHeading}>
            <div>
              <div className="eyebrow">A CLOSER LOOK</div>
              <h2 id="stills-title">Stills for your story.</h2>
            </div>
            <p>1920 × 1080 JPGs. Captions and credits included in the kit.</p>
          </div>
          <div className={styles.stills}>
            {kit.stills.map((still) => (
              <figure key={still.file}>
                <a
                  href={`/media/${still.file}`}
                  download
                  aria-label={`Download ${still.title}`}
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
                  <h3>{still.title}</h3>
                  <p>{still.caption}</p>
                  <a
                    className={styles.textLink}
                    href={`/media/${still.file}`}
                    download
                  >
                    Download JPG <ArrowDownToLine size={15} />
                  </a>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section className={styles.section} aria-labelledby="brand-title">
          <div className={styles.sectionHeading}>
            <div>
              <div className="eyebrow">THE NAME & THE MARK</div>
              <h2 id="brand-title">The Driving Fly.</h2>
            </div>
            <p>The public project name. “Flyhard” is the code project.</p>
          </div>
          <div className={styles.brand}>
            <div className={styles.brandCard}>
              <div className="wordmark">
                <FlyMark size={45} />
                <span>
                  The Driving Fly<span className="wordmark-period">.</span>
                </span>
              </div>
              <div>
                <a href="/press/the-driving-fly-wordmark.svg" download>
                  Wordmark · SVG <ArrowDownToLine size={15} />
                </a>
                <a href="/press/the-driving-fly-wordmark.png" download>
                  PNG <ArrowDownToLine size={15} />
                </a>
              </div>
            </div>
            <div className={styles.brandCard}>
              <FlyMark size={80} />
              <div>
                <a href="/press/the-driving-fly-mark.svg" download>
                  Fly mark · SVG <ArrowDownToLine size={15} />
                </a>
                <a href="/press/the-driving-fly-mark.png" download>
                  PNG <ArrowDownToLine size={15} />
                </a>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="credits-title">
          <div className={styles.sectionHeading}>
            <div>
              <div className="eyebrow">CREDITS & SOURCES</div>
              <h2 id="credits-title">A little credit goes a long way.</h2>
            </div>
          </div>
          <p className={styles.creditIntro}>
            Suggested project credit: “The Driving Fly / Mark Unthank —
            thedrivingfly.com”. Third-party data, imagery, music and sponsor
            marks retain their own terms. Preserve the relevant credits when
            reusing material; contact Mark for original exports or other uses.
          </p>
          <div className={styles.credits}>
            {kit.credits.map((credit) => (
              <div key={credit.title}>
                <h3>{credit.title}</h3>
                <p>{credit.text}</p>
                <a className={styles.textLink} href={credit.url}>
                  Source & details <ArrowUpRight size={14} />
                </a>
              </div>
            ))}
          </div>
          <a className={styles.textLink} href="/press/credits.txt" download>
            Download all credits <ArrowDownToLine size={15} />
          </a>
        </section>

        <section className={styles.contact} aria-labelledby="contact-title">
          <FlyMark size={42} />
          <div>
            <div className="eyebrow">PRESS CONTACT</div>
            <h2 id="contact-title">Talk to the person teaching the fly.</h2>
            <p>Mark Unthank · Creator, The Driving Fly / Really Nice</p>
            <a href={`mailto:${kit.contact}`}>
              {kit.contact} <ArrowUpRight size={17} />
            </a>
          </div>
          <a className="primary" href="https://github.com/MarkUnthank/flyhard">
            Explore the source <ArrowUpRight size={17} />
          </a>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
