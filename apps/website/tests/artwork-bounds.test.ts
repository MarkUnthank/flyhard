import { describe, it, expect } from "vitest";
import { artworkBounds } from "../src/lib/artwork-bounds.mjs";
describe("relocated artwork", () => {
  it("uses the reviewed centre crop for the existing roof ad", () => {
    const span = (1024 / 839) / (1.3532 / .3587);
    expect(artworkBounds(new Uint8ClampedArray(1024 * 839 * 4), 1024, 839,
      [0, .5 - span / 2, 1, span])).toEqual({left: 0, top: 284, width: 1024, height: 271});
  });
  it("removes only transparent gutters, including around rotated artwork", () => {
    const pixels = new Uint8ClampedArray(8 * 6 * 4);
    pixels[(2 * 8 + 1) * 4 + 3] = 1;
    pixels[(4 * 8 + 5) * 4 + 3] = 255;
    expect(artworkBounds(pixels, 8, 6)).toEqual({
      left: 1,
      top: 2,
      width: 5,
      height: 3,
    });
  });
  it("preserves opaque backgrounds", () => {
    const pixels = new Uint8ClampedArray(8 * 6 * 4);
    for (let i = 3; i < pixels.length; i += 4) pixels[i] = 255;
    expect(artworkBounds(pixels, 8, 6)).toEqual({
      left: 0,
      top: 0,
      width: 8,
      height: 6,
    });
  });
  it("keeps a valid full-size region for entirely transparent artwork", () => {
    expect(artworkBounds(new Uint8ClampedArray(8 * 6 * 4), 8, 6)).toEqual({
      left: 0,
      top: 0,
      width: 8,
      height: 6,
    });
  });
});
