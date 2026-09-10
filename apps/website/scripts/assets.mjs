import { copyFile, mkdir, readFile } from "node:fs/promises";
await mkdir("public/draco", { recursive: true });
for (const file of [
  "draco_wasm_wrapper.js",
  "draco_decoder.wasm",
  "draco_decoder.js",
]) {
  await copyFile(
    `node_modules/three/examples/jsm/libs/draco/gltf/${file}`,
    `public/draco/${file}`,
  );
}
for (const file of ["ad-spaces.json", "BarlowCondensed-OFL.txt"]) {
  await copyFile(`../mini-livery/${file}`, `public/model/${file}`);
}
await copyFile("../mini-livery/ad-spaces.json", "src/lib/ad-spaces.json");
console.log(
  "Synced the model, inventory, attribution, and local Draco decoder.",
);

const inventory = JSON.parse(
  await readFile("../mini-livery/ad-spaces.json", "utf8"),
);
await copyFile(
  "../mini-livery/the-driving-fly-mini.glb",
  `public${inventory.model_url}`,
);
