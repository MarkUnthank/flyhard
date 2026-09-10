// Rebuild the site's branded videos and posters from the original recordings.
// Run from apps/website: node scripts/brand-media.mjs
import sharp from "sharp";
import { spawnSync } from "node:child_process";
import { mkdtempSync, renameSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const site = fileURLToPath(new URL("../", import.meta.url));
const root = fileURLToPath(new URL("../../../", import.meta.url));
const temporary = mkdtempSync(join(tmpdir(), "fly-media-"));
function ffmpeg(args) {
  const result = spawnSync(
    "ffmpeg",
    ["-hide_banner", "-loglevel", "error", "-y", ...args],
    { stdio: "inherit" },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error("Media export failed");
}
try {
  const overlay = join(temporary, "brand.png");
  // The source composites reserve their bottom 56 pixels as black margin.
  await sharp(
    Buffer.from(
      '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><text x="960" y="1060" text-anchor="middle" font-family="sans-serif" font-size="28" fill="#eeeeee">thedrivingfly.com</text></svg>',
    ),
  )
    .png()
    .toFile(overlay);
  for (const [name, recording] of [
    ["calm-steering", "carla-calm-v2/flyhard-16x9.mp4"],
    ["faster-steering", "carla-new-yorker-v1/social-16x9.mp4"],
  ]) {
    const source = join(root, "runs", recording);
    const video = join(temporary, `${name}.mp4`);
    const poster = join(temporary, `${name}.jpg`);
    ffmpeg([
      "-i",
      source,
      "-i",
      overlay,
      "-filter_complex",
      "[0:v][1:v]overlay=0:0,scale=1280:720",
      "-c:v",
      "libx264",
      "-crf",
      "25",
      "-preset",
      "fast",
      "-pix_fmt",
      "yuv420p",
      "-an",
      "-movflags",
      "+faststart",
      video,
    ]);
    ffmpeg([
      "-ss",
      "4",
      "-i",
      source,
      "-i",
      overlay,
      "-filter_complex",
      "[0:v][1:v]overlay=0:0",
      "-frames:v",
      "1",
      "-q:v",
      "2",
      poster,
    ]);
    renameSync(video, join(site, "public/media", `${name}.mp4`));
    renameSync(poster, join(site, "public/media", `${name}.jpg`));
  }
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
