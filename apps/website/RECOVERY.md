# September 10 website recovery

The manual release checkout contained website changes that were not committed to GitHub. Git-based releases then replaced them with older source. This recovery branch starts from main after PRs #1–#4 and preserves those merged changes.

## Recovered in this PR

- Slow two-minute car rotation in 3D View. Interaction stops it until reload; Reset does not restart it; reduced-motion preferences disable it. Source: Add auto-spin to 3D View task (01a08a13-ba67-7803-b31b-f0fefde44d07).
- Featured-sponsor bid suggestion, live difference, and Update my bid action. Winning requires at least $1 above the current highest effective bid. Restored alongside the existing plus/minus controls.
- Complimentary sponsor-credit storage, authenticated operator endpoint and CLI, effective bid thresholds, settlement protection, and tests. Original paid history, Stripe payments, and fundraising totals remain unchanged.
- Roof-billboard social images and their composition script, retaining the generated favicon metadata.
- Editable v5 vehicle and accessory Blender sources, source inventory/layout, and rebuild support. Source GLB and inventory are tested against the website assets.

## Already in main and retained

- PR #4: shipped v5 roof-billboard model, matching inventories, crop handling, and model regression test.
- PR #3: historical paid leaderboard with sponsor links, eight compact rows per page, no logos; highest-bid caption/stat; plus/minus controls and selection fix; $1,000 fundraising goal with percentages above 100%; Your brand on the fly’s car headline.
- Hover advertiser previews, drag-and-drop artwork upload, outbid email notifications, and seven active placements from Build TheDrivingFly ad site (01a08788-a1a6-7af0-8c0f-a7245d4bd831).
- Media journal, shared navigation, sponsor links, roundabout film and stills from Add Fly media section (01a08a16-308a-7e40-a482-e63094d81e4f).
- Generated favicon and PR-only release policy from Add site favicon (01a08ae4-d768-7733-b1e9-ee457ba32962).

## Inventory boundaries

Compared the shared website checkout, isolated website release snapshot, media/outbid worktrees, favicon worktree, and roof-billboard source checkout against current main. Formatting-only differences, generated Next declarations, private operational receipts, and QA artifacts are excluded. The ad-blocker preview investigation contained diagnosis, not an implemented patch.

Separate CARLA training/runtime experiments, native asset cooking, and press outreach are not website changes and remain in their original checkouts. No files there are reset or deleted.

This PR restores existing features; it does not grant credits, create charges, send emails, or modify production auction data. Production publication remains the GitHub PR → authorized merge → Cloudflare Builds workflow in the root AGENTS.md.

## Validation

34 automated tests pass, including credit authorization/idempotency, settlement races, original paid history, outbid email behavior, and matching source/public model files. TypeScript and the OpenNext production build pass. Local browser checks use an isolated public-data fixture: eight-row pagination and original links, featured bid calculation/update, plus/minus double-clicks, mobile callout layout, and rotation stopping after interaction. No checkout requests were submitted.
