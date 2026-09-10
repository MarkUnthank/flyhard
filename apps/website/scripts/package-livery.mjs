import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, copyFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

if (!process.argv[2])
  throw new Error(
    "Pass the exported livery directory after Blender has generated its models.",
  );
const source = resolve(process.argv[2]);
const manifest = JSON.parse(
  await readFile(join(source, "livery.json"), "utf8"),
);
if (!Number.isSafeInteger(manifest.revision) || manifest.revision < 0)
  throw new Error("Invalid revision");
if (!Number.isSafeInteger(manifest.layoutVersion))
  throw new Error("Invalid layout version");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const output = join(
  root,
  "mini-livery",
  "sponsors",
  `r${manifest.revision}-layout${manifest.layoutVersion}`,
);
const checksums = JSON.parse(
  await readFile(join(source, "sha256.json"), "utf8"),
);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const files = ["sponsored-mini.blend", "sponsored-mini.glb"];
const sponsors = manifest.placements.map((p) => {
  if (!/^ad-\d+$/.test(p.slotId) || p.texture !== `textures/${p.slotId}.png`)
    throw new Error("Invalid texture path");
  files.push(p.texture);
  return {
    slotId: p.slotId,
    brand: p.brand,
    url: p.url,
    mesh: p.slot.panel,
    texture: p.texture,
    widthMetres: p.slot.width_m,
    heightMetres: p.slot.height_m,
  };
});
const contents = new Map();
for (const name of files) {
  const bytes = await readFile(join(source, name));
  if (checksums[name] && hash(bytes) !== checksums[name])
    throw new Error(`Checksum mismatch: ${name}`);
  contents.set(name, bytes);
}
await mkdir(dirname(output), { recursive: true });
await mkdir(output); // Published revisions are immutable: never replace one silently.
await mkdir(join(output, "textures"));
const hashes = {};
for (const [name, bytes] of contents) {
  await writeFile(join(output, name), bytes);
  hashes[name] = hash(bytes);
}
await writeFile(
  join(output, "manifest.json"),
  JSON.stringify(
    {
      revision: manifest.revision,
      layoutVersion: manifest.layoutVersion,
      source: manifest.source,
      exportedAt: manifest.fetchedAt,
      sponsors,
    },
    null,
    2,
  ) + "\n",
);
hashes["manifest.json"] = hash(await readFile(join(output, "manifest.json")));
await writeFile(
  join(output, "sha256.json"),
  JSON.stringify(hashes, null, 2) + "\n",
);
await copyFile(
  join(root, "mini-livery", "BarlowCondensed-OFL.txt"),
  join(output, "BarlowCondensed-OFL.txt"),
);
console.log(`Prepared public sponsor assets: ${output}`);
console.log(
  "Only public sponsor details and artwork are included. Review before committing.",
);
