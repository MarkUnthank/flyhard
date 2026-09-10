import type { PerspectiveCamera } from "three";

export function resizeViewer(
  camera: PerspectiveCamera,
  renderer: { setSize(width: number, height: number): void },
  width: number,
  height: number,
): boolean {
  // A child effect can run before its parent opens the native dialog.
  // Never let a hidden layout poison the camera with NaN or Infinity.
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  )
    return false;
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.fov = width < 600 ? 45 : 34;
  camera.updateProjectionMatrix();
  return true;
}
