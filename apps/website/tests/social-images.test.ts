import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Miniflare, Response as WorkerResponse } from "miniflare";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import type { Placement } from "../src/lib/auction";
import type { SocialStatus } from "../src/lib/social";
import manifest from "../.social/manifest.json";

let directory: string, script: string, mf: Miniflare;
let options: ConstructorParameters<typeof Miniflare>[0];
let failSquare: boolean, uploadGate: Promise<void> | undefined, uploads: number;
let keys: Awaited<ReturnType<typeof generateKeyPair>>,
  jwk: Awaited<ReturnType<typeof exportJWK>>;
const adminToken = "test-local-operator";
const site = "http://localhost:3000";
type Stub = {
  testSeed(
    revision: number,
    placements: Record<string, Placement>,
  ): Promise<void>;
  testSql(
    query: string,
    ...values: (number | string | null)[]
  ): Promise<Record<string, unknown>[]>;
};
let stub: Stub;
const request = (
  path: string,
  init?: Parameters<Miniflare["dispatchFetch"]>[1],
) => mf.dispatchFetch(`${site}${path}`, init);
const status = async () =>
  (await (await request("/api/social")).json()) as SocialStatus;
const jpeg = (value = 1) => new Uint8Array([0xff, 0xd8, value, 0xff, 0xd9]);
function form(revision = 0, version = manifest.version, value = 1) {
  const body = new FormData();
  body.set("revision", String(revision));
  body.set("rendererVersion", version);
  for (const shape of ["wide", "square"])
    body.set(
      shape,
      new Blob([jpeg(value)], { type: "image/jpeg" }),
      `${shape}.jpg`,
    );
  return body;
}
const publish = async (body = form(), token = adminToken) => {
  const encoded = new Response(body);
  return request("/api/social/publish", {
    method: "POST",
    body: await encoded.arrayBuffer(),
    headers: {
      "Content-Type": encoded.headers.get("Content-Type")!,
      Authorization: `Bearer ${token}`,
    },
  });
};
async function oidc(claims: Record<string, unknown> = {}) {
  return new SignJWT({
    repository_id: "1363155073",
    repository_owner_id: "15160212",
    ref: "refs/heads/main",
    workflow_ref:
      "MarkUnthank/flyhard/.github/workflows/social-images.yml@refs/heads/main",
    event_name: "schedule",
    sub: "repo:MarkUnthank/flyhard:ref:refs/heads/main",
    iss: "https://token.actions.githubusercontent.com",
    aud: `${site}/api/social/publish`,
    iat: Math.floor(Date.now() / 1000),
    nbf: Math.floor(Date.now() / 1000) - 1,
    exp: Math.floor(Date.now() / 1000) + 300,
    ...claims,
  })
    .setProtectedHeader({ alg: "RS256", kid: "test" })
    .sign(keys.privateKey);
}

beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), "flyhard-social-test-"));
  script = join(directory, "worker.mjs");
  keys = await generateKeyPair("RS256");
  jwk = {
    ...(await exportJWK(keys.publicKey)),
    kid: "test",
    alg: "RS256",
    use: "sig",
  };
  await build({
    entryPoints: ["tests/fixtures/social-worker.ts"],
    outfile: script,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    external: ["cloudflare:workers", "node:*"],
  });
});
beforeEach(async () => {
  failSquare = false;
  uploadGate = undefined;
  uploads = 0;
  const storage = join(directory, crypto.randomUUID());
  options = {
    name: "social-test",
    modules: true,
    modulesRoot: directory,
    scriptPath: script,
    compatibilityDate: "2026-07-30",
    compatibilityFlags: ["nodejs_compat"],
    durableObjects: { AUCTION: { className: "Auction", useSQLite: true } },
    durableObjectsPersist: join(storage, "do"),
    r2Persist: join(storage, "r2"),
    r2Buckets: ["ARTWORK"],
    serviceBindings: {
      ASSETS: () =>
        new WorkerResponse("fallback-jpeg", {
          headers: { "Content-Type": "image/jpeg" },
        }),
    },
    bindings: { SITE_URL: site, AUCTION_ADMIN_TOKEN: adminToken },
    outboundService: async (request: import("miniflare").Request) => {
      const url = new URL(request.url);
      if (
        url.href ===
        "https://token.actions.githubusercontent.com/.well-known/jwks"
      )
        return WorkerResponse.json({ keys: [jwk] });
      if (url.origin === "https://social-upload.test") {
        uploads++;
        await uploadGate;
        return new WorkerResponse(null, {
          status: failSquare && url.pathname.endsWith("square.jpg") ? 503 : 200,
        });
      }
      throw new Error(`Unexpected external request: ${url.origin}`);
    },
  };
  mf = new Miniflare(options);
  const namespace = await mf.getDurableObjectNamespace("AUCTION");
  stub = namespace.get(
    namespace.idFromName("the-driving-fly-v1"),
  ) as unknown as Stub;
});
afterEach(async () => {
  await mf?.dispose();
});
afterAll(async () => {
  await rm(directory, { recursive: true, force: true });
});

describe("automatic sponsor social images", () => {
  it("publishes both sizes and serves immutable images with uncached current aliases", async () => {
    expect(await status()).toMatchObject({
      pending: true,
      publishedRevision: null,
    });
    expect(
      (await request("/api/social/wide.jpg")).headers.get("Cache-Control"),
    ).toBe("no-store");
    expect((await publish()).status).toBe(200);
    const ready = await status();
    expect(ready).toMatchObject({
      pending: false,
      publishedRevision: 0,
      rendererVersion: manifest.version,
    });
    expect(ready.images.wide).toBe(
      `/api/social/${manifest.version}-r0/wide.jpg`,
    );
    for (const path of Object.values(ready.images)) {
      const response = await request(path);
      expect(response.headers.get("Cache-Control")).toContain("immutable");
      expect(response.headers.get("Content-Type")).toBe("image/jpeg");
      expect(new Uint8Array(await response.arrayBuffer())).toEqual(jpeg());
      const head = await request(path, { method: "HEAD" });
      expect(await head.text()).toBe("");
      expect(head.headers.get("ETag")).toBe(response.headers.get("ETag"));
      expect(
        (
          await request(path, {
            headers: { "If-None-Match": response.headers.get("ETag")! },
          })
        ).status,
      ).toBe(304);
    }
    const alias = await request("/api/social/wide.jpg", { redirect: "manual" });
    expect(alias.status).toBe(302);
    expect(alias.headers.get("Location")).toContain(ready.images.wide);
    expect(alias.headers.get("Cache-Control")).toBe("no-store");
    expect((await publish(form(0, manifest.version, 2))).status).toBe(200);
    expect(uploads).toBe(2);
  });

  it("authenticates the exact main-branch Actions job using its signed GitHub token", async () => {
    expect((await publish(form(), await oidc())).status).toBe(200);
    expect((await status()).pending).toBe(false);
  });

  it.each([
    { repository_id: "123" },
    { repository_owner_id: "123" },
    { ref: "refs/heads/other" },
    { sub: "repo:MarkUnthank/flyhard:pull_request" },
    { event_name: "pull_request" },
    {
      workflow_ref:
        "MarkUnthank/flyhard/.github/workflows/other.yml@refs/heads/main",
    },
    { aud: "https://another-site.example/api/social/publish" },
    { exp: 1 },
  ])("rejects an untrusted or expired publisher: %j", async (claims) => {
    expect((await publish(form(), await oidc(claims))).status).toBe(401);
    expect(uploads).toBe(0);
  });

  it("rejects unauthenticated, malformed and oversized publications without changing the pair", async () => {
    expect((await publish(form(), "wrong")).status).toBe(401);
    const missing = form();
    missing.delete("square");
    expect((await publish(missing)).status).toBe(400);
    const bad = form();
    bad.set(
      "wide",
      new Blob(["not a jpeg"], { type: "image/jpeg" }),
      "wide.jpg",
    );
    expect((await publish(bad)).status).toBe(400);
    const large = form();
    large.set(
      "wide",
      new Blob([new Uint8Array(4_000_001)], { type: "image/jpeg" }),
      "wide.jpg",
    );
    expect((await publish(large)).status).toBe(413);
    expect((await status()).publishedRevision).toBeNull();
    expect(uploads).toBe(0);
  });

  it("detects new wrap and template revisions and refuses stale renders", async () => {
    await publish();
    const previous = await status();
    await stub.testSeed(1, {});
    expect(await status()).toMatchObject({
      pending: true,
      revision: 1,
      images: previous.images,
    });
    expect((await publish(form(0))).status).toBe(409);
    expect((await publish(form(1, "0".repeat(20)))).status).toBe(409);
    expect((await publish(form(1))).status).toBe(200);
    expect((await status()).images.wide).not.toBe(previous.images.wide);
    expect((await request(previous.images.wide)).status).toBe(200);
    await stub.testSql(
      "UPDATE social_images SET published_key = ?",
      `${"0".repeat(20)}-r1`,
    );
    expect((await status()).pending).toBe(true);
  });

  it("keeps the last pair through a storage failure and retries after restart without overwriting images", async () => {
    await publish();
    const previous = await status();
    await stub.testSeed(1, {});
    failSquare = true;
    expect((await publish(form(1))).status).toBe(500);
    expect((await status()).images).toEqual(previous.images);
    let bucket = await mf.getR2Bucket("ARTWORK");
    const prefix = `social/${manifest.version}-r1`;
    expect(await bucket.get(`${prefix}/wide.jpg`)).not.toBeNull();
    expect(await bucket.get(`${prefix}/square.jpg`)).toBeNull();
    failSquare = false;
    await mf.setOptions({
      ...options,
      bindings: { ...options.bindings, RESTART: "1" },
    });
    bucket = await mf.getR2Bucket("ARTWORK");
    expect((await publish(form(1, manifest.version, 2))).status).toBe(200);
    expect((await status()).publishedRevision).toBe(1);
    expect(
      new Uint8Array(
        await (await bucket.get(`${prefix}/wide.jpg`))!.arrayBuffer(),
      ),
    ).toEqual(jpeg(1));
    expect(
      new Uint8Array(
        await (await bucket.get(`${prefix}/square.jpg`))!.arrayBuffer(),
      ),
    ).toEqual(jpeg(2));
  });

  it("does not promote an upload overtaken by a newer sponsor", async () => {
    await publish();
    await stub.testSeed(1, {});
    let release!: () => void;
    uploadGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const running = publish(form(1));
    await expect.poll(() => uploads).toBe(3);
    await stub.testSeed(2, {});
    release();
    expect((await running).status).toBe(409);
    expect(await status()).toMatchObject({
      pending: true,
      publishedRevision: 0,
    });
    expect((await publish(form(2))).status).toBe(200);
    expect(await status()).toMatchObject({
      pending: false,
      publishedRevision: 2,
    });
  });

  it("returns uncached errors for missing image URLs", async () => {
    for (const path of [
      "/api/social/nonsense/wide.jpg",
      `/api/social/${"a".repeat(20)}-r999/wide.jpg`,
    ]) {
      const response = await request(path);
      expect(response.status).toBe(404);
      expect(response.headers.get("Cache-Control")).toBe("no-store");
    }
  });
});
