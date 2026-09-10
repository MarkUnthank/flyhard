import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import sharp from "sharp";
import { renderSocialCards } from "./render-social.mjs";
import sizes from "../src/lib/social-sizes.json" with { type: "json" };

const { values } = parseArgs({
  options: {
    site: { type: "string", default: "https://thedrivingfly.com" },
    output: { type: "string", default: "artifacts/social" },
    publish: { type: "boolean", default: false },
  },
});
const site = new URL(values.site);
const manifest = JSON.parse(await readFile(".social/manifest.json", "utf8"));
async function getJson(path) {
  const response = await fetch(new URL(path, site), {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}
async function publisherToken() {
  if (process.env.AUCTION_ADMIN_TOKEN) return process.env.AUCTION_ADMIN_TOKEN;
  if (
    !process.env.ACTIONS_ID_TOKEN_REQUEST_URL ||
    !process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN
  )
    throw new Error(
      "Local publishing requires AUCTION_ADMIN_TOKEN. Use npm run social:render for a preview, or run the GitHub Actions workflow.",
    );
  const url = new URL(process.env.ACTIONS_ID_TOKEN_REQUEST_URL);
  url.searchParams.set("audience", new URL("/api/social/publish", site).href);
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN}`,
    },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok)
    throw new Error(`GitHub publisher authentication: HTTP ${response.status}`);
  const { value } = await response.json();
  if (typeof value !== "string" || !value)
    throw new Error("GitHub did not issue a publisher token");
  return value;
}

async function update() {
  if (values.publish) {
    const status = await getJson("/api/social");
    if (!status.pending) {
      console.log("Social images already match the current wrap.");
      return;
    }
    if (status.rendererVersion !== manifest.version)
      throw new Error(
        "This checkout's renderer differs from the deployed website. Wait for Cloudflare Builds, or use the deployed main commit.",
      );
    // Fail before rendering if local publishing has not been configured.
    if (
      !process.env.AUCTION_ADMIN_TOKEN &&
      (!process.env.ACTIONS_ID_TOKEN_REQUEST_URL ||
        !process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN)
    )
      await publisherToken();
  }
  const snapshot = await getJson("/api/livery");
  const images = await renderSocialCards(snapshot, site);
  const output = resolve(values.output);
  await mkdir(output, { recursive: true });
  for (const [shape, bytes] of Object.entries(images)) {
    const metadata = await sharp(bytes).metadata();
    const { width, height } = sizes[shape];
    if (
      metadata.format !== "jpeg" ||
      metadata.width !== width ||
      metadata.height !== height
    )
      throw new Error(`Unexpected ${shape} image dimensions`);
    await writeFile(`${output}/${shape}.jpg`, bytes);
  }
  const receipt = {
    revision: snapshot.revision,
    rendererVersion: manifest.version,
    generatedAt: new Date().toISOString(),
    source: site.origin,
  };
  await writeFile(
    `${output}/receipt.json`,
    JSON.stringify(receipt, null, 2) + "\n",
  );
  console.log(`Rendered wrap revision ${snapshot.revision}: ${output}`);
  if (!values.publish) return;
  const body = new FormData();
  body.set("revision", String(snapshot.revision));
  body.set("rendererVersion", manifest.version);
  for (const [shape, bytes] of Object.entries(images))
    body.set(shape, new Blob([bytes], { type: "image/jpeg" }), `${shape}.jpg`);
  const response = await fetch(new URL("/api/social/publish", site), {
    method: "POST",
    body,
    redirect: "error",
    signal: AbortSignal.timeout(60_000),
    headers: { Authorization: `Bearer ${await publisherToken()}` },
  });
  if (!response.ok)
    throw new Error(
      `Social publication: HTTP ${response.status}. ${await response.text()}`,
    );
  const published = await response.json();
  if (published.publishedRevision !== snapshot.revision)
    throw new Error("Publication revision was not confirmed");
  // Read back both objects, so a successful run proves the new URLs are usable.
  for (const path of Object.values(published.images)) {
    const image = await fetch(new URL(path, site), {
      method: "HEAD",
      signal: AbortSignal.timeout(30_000),
    });
    if (!image.ok || image.headers.get("content-type") !== "image/jpeg")
      throw new Error("Published image readback failed");
  }
  console.log(
    `Published and verified both social images for wrap revision ${snapshot.revision}.`,
  );
}
await update();
