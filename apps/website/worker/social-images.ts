import manifest from "../.social/manifest.json";
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
type Dispatch = { image_key: string; attempts: number; retry_at: number };

/** Publishes a complete pair rendered by GitHub Actions or the local operator. */
export class SocialImages {
  private dispatchWork: Promise<void> | undefined;
  constructor(
    private sql: SqlStorage,
    private env: Env,
    private revision: () => number,
  ) {
    sql.exec(`CREATE TABLE IF NOT EXISTS social_images (
      id INTEGER PRIMARY KEY CHECK (id = 1), published_key TEXT,
      published_revision INTEGER, generated_at INTEGER
    ); INSERT OR IGNORE INTO social_images (id) VALUES (1);
    CREATE TABLE IF NOT EXISTS social_dispatch (
      id INTEGER PRIMARY KEY CHECK (id = 1), image_key TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, retry_at INTEGER NOT NULL DEFAULT 0
    );`);
    // Bootstrap once after deployment, including a changed model or template.
    this.queue();
  }

  private state() {
    return this.sql
      .exec<State>("SELECT * FROM social_images WHERE id = 1")
      .one();
  }
  private key(revision = this.revision()) {
    return `${manifest.version}-r${revision}`;
  }
  /** Called inside the transaction that publishes a winning sponsor. */
  queue() {
    const key = this.key();
    if (this.state().published_key === key) {
      this.sql.exec("DELETE FROM social_dispatch");
      return;
    }
    this.sql.exec(
      `INSERT INTO social_dispatch (id, image_key) VALUES (1, ?)
      ON CONFLICT(id) DO UPDATE SET image_key = excluded.image_key, attempts = 0, retry_at = 0
      WHERE social_dispatch.image_key != excluded.image_key`,
      key,
    );
  }
  private queued() {
    return this.sql
      .exec<Dispatch>("SELECT * FROM social_dispatch WHERE id = 1")
      .toArray()[0];
  }
  nextAttempt(): number | null {
    return this.env.SOCIAL_IMAGES_GITHUB_TOKEN
      ? (this.queued()?.retry_at ?? null)
      : null;
  }
  dispatch(): Promise<void> {
    if (!this.dispatchWork)
      this.dispatchWork = this.sendDispatch().finally(() => {
        this.dispatchWork = undefined;
      });
    return this.dispatchWork;
  }
  private async sendDispatch() {
    const due = this.nextAttempt();
    if (due === null || due > Date.now()) return;
    const job = this.queued()!;
    const attempt = job.attempts + 1;
    // A GitHub acknowledgement is not image publication. Keep this durable job
    // until /publish succeeds, allowing 15 minutes for the 10-minute workflow.
    this.sql.exec(
      "UPDATE social_dispatch SET attempts = ?, retry_at = ? WHERE image_key = ?",
      attempt,
      Date.now() + 15 * 60_000,
      job.image_key,
    );
    try {
      const response = await fetch(
        "https://api.github.com/repos/MarkUnthank/flyhard/actions/workflows/social-images.yml/dispatches",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this.env.SOCIAL_IMAGES_GITHUB_TOKEN}`,
            Accept: "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "the-driving-fly",
            "X-GitHub-Api-Version": "2026-03-10",
          },
          body: JSON.stringify({ ref: "main" }),
          signal: AbortSignal.timeout(15_000),
        },
      );
      if (!response.ok)
        throw new Error(`GitHub returned HTTP ${response.status}`);
      await response.body?.cancel();
      console.info(
        JSON.stringify({
          event: "social_workflow_dispatched",
          key: job.image_key,
          attempt,
        }),
      );
    } catch (error) {
      // Only pending work retries; there is no periodic Actions run or idle poll.
      this.sql.exec(
        "UPDATE social_dispatch SET retry_at = ? WHERE image_key = ?",
        Date.now() +
          Math.min(15 * 60_000, 60_000 * 2 ** Math.min(attempt - 1, 4)),
        job.image_key,
      );
      console.error(
        JSON.stringify({
          event: "social_workflow_retry",
          key: job.image_key,
          attempt,
          error:
            error instanceof Error
              ? error.message.slice(0, 150)
              : "Dispatch failed",
        }),
      );
    }
  }
  status(): SocialStatus {
    const state = this.state();
    const revision = this.revision();
    return {
      revision,
      publishedRevision: state.published_revision,
      pending: state.published_key !== this.key(revision),
      triggerConfigured: Boolean(this.env.SOCIAL_IMAGES_GITHUB_TOKEN),
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
    const bytes = await readBody(request, 4_100_000); // Both 2 MB JPEGs plus multipart framing.
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
    if (this.state().published_key === key) {
      this.sql.exec("DELETE FROM social_dispatch WHERE image_key = ?", key);
      return json(this.status());
    }

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
    this.sql.exec("DELETE FROM social_dispatch WHERE image_key = ?", key);
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
