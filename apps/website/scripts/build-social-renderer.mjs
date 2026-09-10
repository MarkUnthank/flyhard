// The renderer fingerprint must match between the publisher and deployed Worker.
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { relative } from "node:path";

const outdir = "public/social/renderer";
async function writeChanged(path, bytes) {
  const existing = await readFile(path).catch(() => null);
  if (!existing?.equals(Buffer.from(bytes))) await writeFile(path, bytes);
}
const result = await build({
  entryPoints: { index: "src/social/card.tsx" },
  outdir,
  bundle: true,
  minify: true,
  platform: "browser",
  target: "es2022",
  format: "iife",
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff2": "file", ".woff": "file" },
  write: false,
});
const inventory = JSON.parse(await readFile("src/lib/ad-spaces.json", "utf8"));
const assets = [
  inventory.model_url,
  "/draco/draco_wasm_wrapper.js",
  "/draco/draco_decoder.wasm",
  "/draco/draco_decoder.js",
];
const hash = createHash("sha256");
for (const path of [
  "scripts/render-social.mjs",
  "src/lib/social.ts",
  "src/lib/social-sizes.json",
  "package-lock.json",
])
  hash.update(path).update(await readFile(path));
for (const path of assets) {
  hash.update(path).update(await readFile(`public${path}`));
}
await mkdir(outdir, { recursive: true });
for (const file of result.outputFiles.sort((a, b) =>
  a.path < b.path ? -1 : 1,
)) {
  const path = `/${relative("public", file.path)}`;
  assets.push(path);
  hash.update(path).update(file.contents);
  await writeChanged(file.path, file.contents);
}
await mkdir(".social", { recursive: true });
await writeChanged(
  ".social/manifest.json",
  JSON.stringify(
    { version: hash.digest("hex").slice(0, 20), assets },
    null,
    2,
  ) + "\n",
);
console.log("Built social-card renderer and model fingerprint.");
