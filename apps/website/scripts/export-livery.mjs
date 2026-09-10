import { mkdir, readFile, writeFile, copyFile } from "node:fs/promises";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const origin = "https://thedrivingfly.com";
async function download(path) {
  const response = await fetch(new URL(path, origin));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
}
const snapshot = JSON.parse(await download("/api/livery"));
const inventory = JSON.parse(await download("/model/ad-spaces.json"));
if (!Array.isArray(snapshot.activeSlotIds))
  throw new Error("Deploy the current inventory before exporting.");
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const output = resolve(
  process.argv[2] ||
    join(root, "exports", `livery-r${snapshot.revision}-${stamp}`),
);
await mkdir(dirname(output), { recursive: true });
// Never overwrite an earlier recording's frozen livery.
await mkdir(output);
await mkdir(join(output, "textures"));
const checksums = {};
async function save(name, data) {
  await writeFile(join(output, name), data);
  checksums[name] = createHash("sha256").update(data).digest("hex");
}
const placements = [];
for (const placement of Object.values(snapshot.placements)) {
  const slot = inventory.slots.find((s) => s.id === placement.slotId);
  if (!slot || !/^ad-\d+$/.test(slot.id))
    throw new Error("Unknown published slot");
  if (!snapshot.activeSlotIds.includes(slot.id))
    throw new Error("A paid spot is missing from the active inventory");
  for (const field of ["textureUrl", "logoUrl"]) {
    if (!/^\/api\/artwork\/[a-f0-9-]{36}\.png$/.test(placement[field]))
      throw new Error("Unexpected artwork URL");
  }
  const texture = `textures/${slot.id}.png`;
  const logo = `textures/${slot.id}-logo.png`;
  await save(texture, await download(placement.textureUrl));
  await save(logo, await download(placement.logoUrl));
  placements.push({ ...placement, slot, texture, logo });
}
await save("source-mini.glb", await download(inventory.model_url));
await save("inventory.json", JSON.stringify(inventory, null, 2));
await save("snapshot.json", JSON.stringify(snapshot, null, 2));
await save(
  "livery.json",
  JSON.stringify(
    {
      source: origin,
      fetchedAt: new Date().toISOString(),
      revision: snapshot.revision,
      layoutVersion: inventory.layout_version,
      activeSlotIds: snapshot.activeSlotIds,
      placements,
    },
    null,
    2,
  ),
);
await copyFile(
  join(root, "scripts", "apply-livery.py"),
  join(output, "apply-livery.py"),
);
await copyFile(join(root, "LIVERY-EXPORT.md"), join(output, "README.md"));
await save(
  "CREDITS.md",
  await readFile(join(root, "..", "mini-livery", "README.md")),
);
await save(
  "BarlowCondensed-OFL.txt",
  await readFile(join(root, "..", "mini-livery", "BarlowCondensed-OFL.txt")),
);
await writeFile(
  join(output, "sha256.json"),
  JSON.stringify(checksums, null, 2),
);
console.log(
  JSON.stringify(
    { output, revision: snapshot.revision, sponsors: placements.length },
    null,
    2,
  ),
);
console.log(
  `Build the textured model: blender --background --python-exit-code 1 --python "${join(output, "apply-livery.py")}" -- "${output}"`,
);
