/** Find visible artwork when moving a logo to a differently shaped panel.
 * Only transparent gutters are removed; opaque backgrounds and rotation remain.
 * @param {ArrayLike<number>} rgba
 * @param {number} width
 * @param {number} height
 * @param {number[]} [cropRule]
 */
export function artworkBounds(rgba, width, height, cropRule) {
  // A reviewed placement move can retain an exact crop of its current artwork.
  // The caller selects a rule by immutable texture URL; future buyers use full UVs.
  if (cropRule) {
    const [x, y, w, h] = cropRule;
    const left = Math.round(x * width), top = Math.round(y * height);
    return { left, top, width: Math.min(width - left, Math.round(w * width)),
      height: Math.min(height - top, Math.round(h * height)) };
  }
  let left = width,
    top = height,
    right = -1,
    bottom = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (rgba[(y * width + x) * 4 + 3] === 0) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x);
      bottom = Math.max(bottom, y);
    }
  }
  return right < 0
    ? { left: 0, top: 0, width, height }
    : { left, top, width: right - left + 1, height: bottom - top + 1 };
}
