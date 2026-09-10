import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import inventory from "../src/lib/ad-spaces.json";

it("ships the advertised model and matching public inventory", () => {
  const publicRoot = resolve(import.meta.dirname, "../public");
  expect(JSON.parse(readFileSync(resolve(publicRoot, "model/ad-spaces.json"), "utf8"))).toEqual(inventory);
  const glb = readFileSync(resolve(publicRoot, inventory.model_url.slice(1)));
  expect(readFileSync(resolve(import.meta.dirname, "../../mini-livery/the-driving-fly-mini.glb"))).toEqual(glb);
  expect(JSON.parse(readFileSync(resolve(import.meta.dirname, "../../mini-livery/ad-spaces.json"), "utf8"))).toEqual(inventory);
  expect(new TextDecoder().decode(glb.subarray(0, 4))).toBe("glTF");
  const jsonLength = new DataView(glb.buffer, glb.byteOffset, glb.byteLength).getUint32(12, true);
  const model = JSON.parse(new TextDecoder().decode(glb.subarray(20, 20 + jsonLength)));
  const nodes = new Set(model.nodes.map((node: { name: string }) => node.name));
  for (const slot of inventory.slots) expect(nodes.has(slot.panel), slot.panel).toBe(true);
  expect(model.nodes.some((node: { extras?: { role?: string } }) => node.extras?.role === "billboard_structure")).toBe(true);
});
