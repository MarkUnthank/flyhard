import { PerspectiveCamera, Vector3 } from "three";
import { expect, it, vi } from "vitest";
import { resizeViewer } from "../src/lib/viewer-size";

it("keeps a hidden dialog camera finite until it opens, including repeated opens", () => {
  const camera = new PerspectiveCamera(34, 1, 0.1, 100);
  const renderer = { setSize: vi.fn() };
  for (const [width, height] of [
    [0, 0],
    [390, 220],
    [0, 0],
    [800, 500],
  ]) {
    const previousAspect = camera.aspect;
    const visible = resizeViewer(camera, renderer, width, height);
    expect(visible).toBe(width > 0 && height > 0);
    expect(camera.aspect).toBe(visible ? width / height : previousAspect);
    expect(camera.projectionMatrix.elements.every(Number.isFinite)).toBe(true);
    // Exercise the same aspect-dependent framing that used to propagate NaN.
    const destination = new Vector3(3.3, 2.65, -4.4).multiplyScalar(
      Math.max(1, 1.05 / camera.aspect),
    );
    camera.position.lerp(destination, 0.09);
    expect(camera.position.toArray().every(Number.isFinite)).toBe(true);
  }
  expect(renderer.setSize.mock.calls).toEqual([
    [390, 220],
    [800, 500],
  ]);
});

it.each([
  [0, 200],
  [200, 0],
  [NaN, 200],
  [200, Infinity],
])("ignores invalid viewport %s by %s", (width, height) => {
  const camera = new PerspectiveCamera();
  const renderer = { setSize: vi.fn() };
  expect(resizeViewer(camera, renderer, width, height)).toBe(false);
  expect(renderer.setSize).not.toHaveBeenCalled();
  expect(camera.projectionMatrix.elements.every(Number.isFinite)).toBe(true);
});
