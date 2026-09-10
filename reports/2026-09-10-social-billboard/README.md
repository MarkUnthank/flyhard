# Billboard social cards and featured minimum

Deployed version `fa30d60d-b1a2-49f8-a5b3-9a2d4fd1af52` to thedrivingfly.com.

- Open Graph and Twitter metadata now reference `driving-fly-wide-v4.jpg`
  (1200 × 630); the secondary square OG card is `driving-fly-square-v4.jpg`
  (1080 × 1080). Both use the current paid billboard model, rendered in Blender
  from fresh production revision 12 / layout 5. Source snapshot:
  `work/live-livery/20260910T093443239046Z`.
- Reproducible rendering: `scripts/render_social_car.py`; card composition:
  `apps/website/scripts/build-social.mjs`. Production image hashes match local
  reviewed files; HTML metadata points to the new versioned URLs.
- Featured-sponsor callout minimum changed from `highestBid + 1` cent to
  `highestBid + 100` cents, still bounded by the chosen placement's minimum.
  Live UI verified with a $6 highest bid: input $6 says "Bid $1 more" and minimum
  $7; $6.01 says "Bid $0.99 more"; $7 shows the qualifying message. No purchase
  was submitted. This change is to the callout calculation, not payment rules.
- TypeScript, 23 integration/artwork tests and production build passed.

## Correction to prior release record

The preceding roof-billboard release used too old a frontend baseline. Despite
the prior report describing media and hover/editor changes as pending, those
features had already shipped by commit 0a19dcf and its earlier deployments. The
previous release inadvertently made `/media` return 404 and removed its navigation.
This release restores that existing frontend (including media files, navigation,
hover preview and artwork editor) while retaining the billboard and this task's
UI changes. `/media` now returns 200 with the roundabout content, and the production
browser again shows "Videos & data". The exact previously deployed auction module
remains in use; no sponsor bids, purchases or credits were modified.
