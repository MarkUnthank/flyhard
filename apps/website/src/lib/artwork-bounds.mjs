/** Find visible artwork when moving a logo to a differently shaped panel.
 * Only transparent gutters are removed; opaque backgrounds and rotation remain.
 * @param {ArrayLike<number>} rgba
 * @param {number} width
 * @param {number} height
 */
export function artworkBounds(rgba, width, height) {
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
