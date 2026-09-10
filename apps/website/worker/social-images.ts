import manifest from "../.social/manifest.json";
import type { AuctionSnapshot } from "../src/lib/auction";
import {
  socialFallbacks,
  socialImagePath,
  type SocialStatus,
  type SocialShape,
} from "../src/lib/social";
import type { Env } from "./env";
import { HttpError, json, readBody } from "./http";
import { authorizeSocialPublisher } from "./social-auth";

type State = {
  published_key: string | null;
  published_revision: number | null;
  generated_at: number | null;
};

/** Publishes a complete pair rendered by GitHub Actions or the local operator. */
export class SocialImages {
  constructor(
    private sql: SqlStorage,
    private env: Env,
    private snapshot: () => AuctionSnapshot,
  ) {
    sql.exec(`CREATE TABLE IF NOT EXISTS social_images (
      id INTEGER PRIMARY KEY CHECK (id = 1), published_key TEXT,
      published_revision INTEGER, generated_at INTEGER
    ); INSERT OR IGNORE INTO social_images (id) VALUES (1);`);
  }

  private state() {
    return this.sql
      .exec<State>("SELECT * FROM social_images WHERE id = 1")
      .one();
  }
  private key(revision = this.snapshot().revision) {
    return `${manifest.version}-r${revision}`;
  }
  status(): SocialStatus {
    const state = this.state();
    const revision = this.snapshot().revision;
    return {
      revision,
      publishedRevision: state.published_revision,
      pending: state.published_key !== this.key(revision),
      rendererVersion: manifest.version,
      generatedAt: state.generated_at,
      images: {
        wide: state.published_key
          ? socialImagePath(state.published_key, "wide")
          : "/api/social/wide.jpg",
        square: state.published_key
          ? socialImagePath(state.published_key, "square")
          : "/api/social/square.jpg",
      },
    };
  }

  async publish(request: Request): Promise<Response> {
    await authorizeSocialPublisher(request, this.env);
    const bytes = await readBody(request, 4_000_000);
    let form: FormData;
    try {
      form = await new Response(bytes.buffer as ArrayBuffer, {
        headers: { "Content-Type": request.headers.get("Content-Type") ?? "" },
      }).formData();
    } catch {
      throw new HttpError(400, "Expected multipart images and revision.");
    }
    const revision = form.get("revision");
    if (
      typeof revision !== "string" ||
      !/^\d+$/.test(revision) ||
      !Number.isSafeInteger(Number(revision))
    )
      throw new HttpError(400, "Invalid wrap revision.");
    const key = `${form.get("rendererVersion")}-r${revision}`;
    if (key !== this.key())
      throw new HttpError(
        409,
        "The wrap or renderer changed. Render the latest version.",
      );
    if (this.state().published_key === key) return json(this.status());

    const images = {} as Record<SocialShape, Uint8Array>;
    for (const shape of ["wide", "square"] as const) {
      const file = form.get(shape);
      if (
        !(file instanceof File) ||
        file.type !== "image/jpeg" ||
        file.size < 4 ||
        file.size > 2_000_000
      )
        throw new HttpError(
          400,
          "Both JPEG images are required (maximum 2 MB each).",
        );
      const image = new Uint8Array(await file.arrayBuffer());
      if (
        image[0] !== 0xff ||
        image[1] !== 0xd8 ||
        image.at(-2) !== 0xff ||
        image.at(-1) !== 0xd9
      )
        throw new HttpError(400, "Invalid JPEG image.");
      images[shape] = image;
    }
    // A failed second write leaves the last pair active. Conditional writes
    // make retries and overlapping publishers safe for immutable image URLs.
    for (const shape of ["wide", "square"] as const) {
      await this.env.ARTWORK.put(`social/${key}/${shape}.jpg`, images[shape], {
        onlyIf: { etagDoesNotMatch: "*" },
        httpMetadata: {
          contentType: "image/jpeg",
          cacheControl: "public, max-age=31536000, immutable",
        },
      });
    }
    // Payments may arrive during R2 writes; an obsolete render must not become current.
    if (key !== this.key())
      throw new HttpError(
        409,
        "The wrap changed during publication. Render it again.",
      );
    this.sql.exec(
      "UPDATE social_images SET published_key = ?, published_revision = ?, generated_at = ? WHERE id = 1",
      key,
      Number(revision),
      Date.now(),
    );
    console.info(
      JSON.stringify({
        event: "social_images_published",
        key,
        revision: Number(revision),
      }),
    );
    return json(this.status());
  }

  async image(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    const alias = /^\/api\/social\/(wide|square)\.jpg$/.exec(path);
    if (alias) {
      const shape = alias[1] as SocialShape;
      const state = this.state();
      if (state.published_key)
        return new Response(null, {
          status: 302,
          headers: {
            Location: new URL(
              socialImagePath(state.published_key, shape),
              this.env.SITE_URL,
            ).href,
            "Cache-Control": "no-store",
          },
        });
      // The existing card remains usable while the first automatic render runs.
      const fallback = await this.env.ASSETS.fetch(
        new Request(new URL(socialFallbacks[shape], this.env.SITE_URL)),
      );
      const headers = new Headers(fallback.headers);
      headers.set("Cache-Control", "no-store");
      headers.delete("ETag");
      return new Response(request.method === "HEAD" ? null : fallback.body, {
        status: fallback.status,
        headers,
      });
    }
    const match =
      /^\/api\/social\/([a-f0-9]{20}-r\d+)\/(wide|square)\.jpg$/.exec(path);
    if (!match) throw new HttpError(404, "Social image not found.");
    const object = await this.env.ARTWORK.get(
      `social/${match[1]}/${match[2]}.jpg`,
    );
    if (!object) throw new HttpError(404, "Social image not found.");
    const headers = new Headers({
      "Content-Type": "image/jpeg",
      "Cache-Control": "public, max-age=31536000, immutable",
      ETag: object.httpEtag,
      "X-Content-Type-Options": "nosniff",
    });
    if (request.headers.get("If-None-Match") === object.httpEtag)
      return new Response(null, { status: 304, headers });
    return new Response(request.method === "HEAD" ? null : object.body, {
      headers,
    });
  }
}
