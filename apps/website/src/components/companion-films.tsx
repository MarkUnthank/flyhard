import { mediaEntries } from "@/lib/media";

type Film = NonNullable<
  (typeof mediaEntries)[number]["companionFilms"]
>[number];

export default function CompanionFilms({ films }: { films: Film[] }) {
  return (
    <section aria-label="Parking film packet">
      <h3>The complete parking packet</h3>
      <p>
        The single attempt and the original 50-attempts film belong together,
        alongside the shorter edit.
      </p>
      {films.map((film) => (
        <figure key={film.file} className="journal-film">
          <h4>{film.title}</h4>
          <video
            controls
            playsInline
            preload="none"
            poster={`/media/${film.file.replace(/\.mp4$/, ".jpg")}`}
            aria-label={film.title}
            style={{ width: "100%" }}
          >
            <source src={`/media/${film.file}`} type="video/mp4" />
            <a href={`/media/${film.file}`}>Download this recording</a>
          </video>
          <figcaption>
            <span>
              {film.description} Sound: {film.audio}.
            </span>
            <a href={`/media/${film.file}`} download>
              Download film
            </a>
          </figcaption>
        </figure>
      ))}
    </section>
  );
}
