import { ArrowDownToLine, ArrowUpRight } from "lucide-react";
import type { mediaEntries } from "@/lib/media";
import styles from "./companion-films.module.css";

type Film = NonNullable<
  (typeof mediaEntries)[number]["companionFilms"]
>[number] & {
  paragraphs?: string[];
};

export default function CompanionFilms({ films }: { films: Film[] }) {
  return (
    <section className={styles.packet} aria-label="Parking film packet">
      <header className={styles.heading}>
        <h3>The complete parking packet</h3>
        <p>
          The single attempt and the original 50-attempts film, alongside the
          shorter edit.
        </p>
      </header>
      <div className={styles.films}>
        {films.map((film) => (
          <figure key={film.file} className={styles.film}>
            <video
              controls
              playsInline
              preload="none"
              poster={`/media/${film.file.replace(/\.mp4$/, ".jpg")}`}
              aria-label={film.title}
            >
              <source src={`/media/${film.file}`} type="video/mp4" />
              <a href={`/media/${film.file}`}>Download this recording</a>
            </video>
            <figcaption>
              <h4>{film.title}</h4>
              <p>{film.description}</p>
              <p>Sound: {film.audio}.</p>
              <a href={`/media/${film.file}`} download>
                Download film <ArrowDownToLine size={15} />
              </a>
              {film.paragraphs && (
                <details>
                  <summary>Transcript &amp; audio description</summary>
                  {film.paragraphs.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                </details>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
      <a className={styles.notes} href="/media#parallel-parking">
        Read the parking field notes <ArrowUpRight size={15} />
      </a>
    </section>
  );
}
