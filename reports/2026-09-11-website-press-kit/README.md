# Latest media and press kit

Adds five finished films from the CARLA experiment task to `/media`, keeping the
three previously published films, and introduces `/press`. The new films are the
final single-attempt three-point turn, dynamic horn etiquette, road rage, faster
Mozart parking edit and indicator close-up. Historical/superseded edits are not
presented as the current film.

The press page provides background, contact, results and limits, separate MP4
downloads, 1080p stills, SVG/PNG brand assets, captions, source credits, and a
24-file ZIP (approximately 990 KiB). The public notes link immutable commits for
the source reports. Six copied result/audit files are unchanged from those
reports. Private runtime, billing and machine-configuration files are excluded.

## Media checks

- All five new files decode completely with FFmpeg.
- H.264, 1920 × 1080, 60 fps; durations 22.8 / 20 / 37.5 / 30 / 25 seconds.
- The three-point-turn and parking compressed video streams are remuxed; the
  other three use bounded-rate H.264 web encodes. There are no additional cuts or
  speed changes. All source frame counts remain intact.
- All four audio streams match the source AAC stream hashes exactly. The
  indicator close-up is silent. Music/horn sources and terms were checked.
- Each MP4 is below Cloudflare's 25 MiB static-asset limit (largest: 15.55 MiB).
- The source and website hashes and exact stream metadata are in
  `apps/website/public/press/data/web-exports.json`.
- Browser playback and seeking to the final half-second succeeded for all eight
  films without media errors. Existing 720p steering files remain unchanged.

## Website checks

- `npm run check`: TypeScript, all 90 tests across eight files, and OpenNext
  Cloudflare build passed. Final caption/layout refinements were typechecked and
  the Worker was rebuilt.
- Local `/media` and `/press` rendered with the intended metadata and canonical
  paths; `/press` is in the sitemap.
- All 32 referenced media assets and all 24 distinct press-page asset URLs
  returned HTTP 200. Every file under `public/press` downloaded byte-identically.
- Next.js development MP4 range requests returned HTTP 206 and the requested
  1,024 bytes. The local Wrangler asset emulator instead returned the full file
  with HTTP 200; deployed range behavior must be rechecked after release.
- The compiled Worker locally served both pages, the ZIP, CSV and SVG with
  HTTP 200 and the expected content types.
- ZIP integrity check passed; 24 entries, including four captioned stills,
  logos, font notice, background, credits, full attribution and evidence.
- Mobile 390 px and tablet 768 px browser layouts had no page overflow. Desktop
  layout and the press-to-film navigation were inspected. The navigation strip
  scrolls at narrower widths, with all seven links retained.
- Selected stills and the generated logo PNG were visually inspected. The
  three-point-turn still caption was corrected to match the forward phase.

## Evidence boundaries

Parking remains 0/50; the three-point-turn held-out result is 6/8 full passes,
with no contacts or boundary crossings in eight cases. The featured take is a
separate successful validation trial. The dynamic horn edit retains an 83 ms
false chirp; road rage retains its failed take and collision. The parking fly
panel is explicitly an independent replay. Engineered inputs, motor assistance,
computed neural states and compositing are disclosed in page copy and notes.

## Release state

Prepared from latest `origin/main` at `f9765cd9dea78c47a11767df78f98fab8e11eec7`.
Its GitHub Workers Builds check succeeded (build
`7d2390f1-b454-46bb-860b-1ddb0aabe400`). The production deployment readback showed
version `ea3f3470-3e4d-4309-83a2-31147f09e7d1`, created September 10 at 16:05 UTC,
after that main commit. The live media page still showed the existing three
films. A direct Python HTTP read of production returned 403, so no byte-for-byte
production bundle comparison is claimed. Reconcile again before an authorized
merge. No production upload, deployment or merge was performed for this task.
