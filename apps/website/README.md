# The Driving Fly website

Next.js 16, OpenNext for Cloudflare Workers, Three.js, Stripe Checkout, one SQLite-backed Durable Object, and R2. All application code lives here; the source model remains in `../mini-livery`.

## Run locally

```sh
npm ci
npm run dev
```

Open http://localhost:3000. Next.js runs on 3000 and proxies `/api/*`, including WebSockets, to the local Worker on 8788. Wrangler provides persistent local R2 and Durable Object storage. `npm run assets` refreshes the website copy of the GLB, its authoritative inventory, and the self-hosted Draco decoder.

Local development automatically reads `STRIPE_TEST_API_KEY` from the repository root `.env` and writes it as the Worker's `STRIPE_API_KEY` in the ignored, private `.dev.vars`. Only test secret/restricted keys are accepted through this setting; the root live key is not used for local checkout. Production still uses the explicit Cloudflare `STRIPE_API_KEY` secret.

For real Stripe test Checkout and signed local webhooks, install the Stripe CLI and run this in another terminal:

```sh
npm run stripe:listen
```

The listener saves its real signing secret to `.dev.vars`. Restart `npm run dev` after connecting the listener so Wrangler reloads the secrets. A restricted test key needs Checkout Sessions write/read, applicable Payment Intents/refund permissions, and **Debugging Tools → Write** for the CLI listener. You can give the listener a separate credential using `STRIPE_CLI_API_KEY` in the root `.env`; that credential is never used by the website. The UI disables checkout until both an API key and webhook signing secret are present.

## Deploy to Cloudflare

The site is deployed with OpenNext to Cloudflare account `94f9d97fe2538adb3efe55c05b63637d`:

| Environment | URL                                                   | Worker                    | Payments    |
| ----------- | ----------------------------------------------------- | ------------------------- | ----------- |
| Production  | https://thedrivingfly.com                             | `the-driving-fly`         | Stripe live |
| Staging     | https://the-driving-fly-staging.mxunthank.workers.dev | `the-driving-fly-staging` | Stripe test |

Production owns both custom domains; `www.thedrivingfly.com` redirects to the apex while preserving the path and query. Staging pages send `X-Robots-Tag: noindex, nofollow`. Each environment has its own SQLite Durable Object and private R2 bucket (`the-driving-fly-artwork` and `the-driving-fly-artwork-staging`). Test purchases cannot change production placements.

Production releases use a pull request targeting the latest `main`. Run the
local checks, reconcile any live changes, and obtain merge authorization.
Cloudflare Builds deploys the merged commit; verify that build and the live
result. See the repository [release rules](../../AGENTS.md). Do not manually
publish production Worker code or assets from a local checkout.

```sh
npm run check
```

The top-level Wrangler configuration is production; `--env staging` selects the isolated test environment. Refresh binding types with `npm run cf:types` after changing bindings.

Both environments already have `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` installed as encrypted Worker secrets. Production uses the supplied live key; staging uses the supplied test key. To rotate them, use `wrangler secret put` (add `--env staging` for staging). Never put keys into `wrangler.jsonc` or source control. Local `.env` changes do not automatically update deployed secrets.

The registered Stripe endpoints are:

- Production: `we_1UDsFWICnIO9a7HSrk4jqjss`, `https://thedrivingfly.com/api/stripe/webhook`.
- Staging: `we_1UDsCnICnIO9a7HSQv33ZTee`, `https://the-driving-fly-staging.mxunthank.workers.dev/api/stripe/webhook`.

Each listens for `checkout.session.completed` and `checkout.session.async_payment_succeeded` in its matching payment mode. When rotating a webhook secret, use that exact endpoint's signing secret.

After deploying, verify `/api/auction` reports `paymentsEnabled: true` and the expected `paymentMode`. Exercise payments on staging and observe the new artwork in another open browser. Production R2 remains private; the Worker serves only artwork linked to a published purchase.

The September 9, 2026 launch deployed production version `6344a20f-a162-4b0f-883c-85c2fb6663d7` and staging version `1bd5d26f-9d38-4b56-935f-9d701ae4ce9a`. Production began with all 59 spots unclaimed at $1. A real live-mode $1 Checkout session was created, verified, and expired without payment. A correctly signed completion request for that unpaid session returned HTTP 200 without publishing an ad. HTTPS, the homepage, API, model asset, and `www` redirect passed checks; the apex checks used public DNS resolution because the local OS still cached its earlier missing record.

On the deployed staging Worker, a $1 sandbox purchase and a $2 replacement both completed through Stripe and delivered successful signed webhooks. An independent headless browser received the replacement over WebSockets and loaded its new R2 texture without a page refresh. These are test purchases only; no live charge was made.

## Custom wrap package

A full custom wrap and two videos start at $10,000, paid immediately through Stripe. Each confirmed purchase increases the next price by $1 and emails the operator. See [Custom wraps](CUSTOM-WRAPS.md) for production, notification configuration and recovery details.

## Payment rules and recovery

- The auction offers seven active spots, defined in the model inventory. All seven existing sponsors are preserved. Supertask remains on the rear window; other paid placements occupy the large doors, front window, bonnet, roof and grille. New advertisers must outbid an existing owner. The homepage shows the live minimum bid. Relocated artwork is fitted to changed panel proportions, removing transparent gutters while preserving logos and opaque backgrounds. The list defaults to sold first, then physical layout order. Retired spots cannot start new checkouts. A legacy payment already in flight remains honoured, even if that temporarily exceeds seven paid spots.
- Empty spots start at 100 USD cents. A new bid must be at least one dollar higher than the currently published bid. Buyers pay the full amount, not the increment.
- Checkout creation never reserves a spot. The server stores a validated immutable bid before creating a Stripe session. A stable Stripe idempotency key makes network retries safe.
- Signed webhooks and checkout-return verification both re-read the session from Stripe. Amount, currency, payment mode, bid identity, session, and successful payment status must match.
- Publication compares the bid to the latest winner and commits the replacement, history, and revision in one synchronous SQL transaction. Duplicate deliveries cannot publish twice or reduce the price.
- If an already-paid bid loses before publication, the server requests a full Stripe refund with a stable idempotency key. If it was published first and then outbid, it is not refunded.
- A Durable Object alarm reconciles pending checkouts and refunds, including missed webhooks and disconnected browsers. A refund that is pending is retrieved by its refund ID on subsequent runs. Stripe-failed or action-required refunds remain `refund_pending`: investigate them in Stripe and the Durable Object records; never describe a refund as completed until Stripe reports `succeeded`.
- Abandoned uploads and expired-checkout artwork are removed after 24 hours. Public data excludes Stripe identifiers and billing details.
- Manual refunds, disputes, ad moderation, and account-support requests need operator handling. This version does not include an admin console or automatically remove previously published ads for chargebacks. The public policy text and receipt support contact should be reviewed before launch.

## Outbid emails

Confirmed replacements now notify the previous owner using their private Stripe Checkout email. Cloudflare Email Service delivers the message; the auction's SQLite outbox and alarm recover temporary failures. Existing sponsors are supported by retrieving their original paid Checkout when displaced. Emails link directly to the spot's current bid form. See [OUTBID-NOTIFICATIONS.md](./OUTBID-NOTIFICATIONS.md) for configuration, sandbox isolation, delivery guarantees and operator checks.

## Live texture workflow

For recording-ready PNGs and a sponsor-textured Blender/glTF model, run `npm run export:livery` and follow [LIVERY-EXPORT.md](./LIVERY-EXPORT.md). Every export freezes one revision; it never modifies the live auction.

1. The browser fits the uploaded logo to the selected surface, then applies the buyer’s scale, rotation, and horizontal/vertical position. The buyer can drag the 2D preview or use sliders and reset. The exact spot boundary crops overflow. The default transparent background preserves PNG/WebP alpha; an optional solid color fills the entire spot. The transformed artwork is encoded as a PNG. The checkout model immediately previews this exact image on the selected, outlined panel; other visitors continue to see the confirmed livery.
2. The browser also prepares a separate logo thumbnail from the original upload (up to 512 pixels), preserving transparency without applying the car placement's crop, position, or rotation. Checkout collects the advertiser's name, HTTPS website, and optional message of up to 140 characters. The Worker size-checks, decodes, and re-encodes both PNGs, strips metadata, and stores them under immutable random R2 keys **before** checkout. Both images stay private until publication and are bound to the same immutable bid.
3. Once payment is verified, the transaction publishes the artwork and logo URLs, name, message, and website together and increments the livery revision. The auction table gives the advertiser the wide first column. Existing purchases receive an empty message and use their previously published artwork as the logo during the storage migration.
4. The Durable Object broadcasts the snapshot over a hibernating WebSocket. Clients reconnect with backoff and also refresh every 15 seconds as a fallback.
5. The Three.js viewer loads the new image and replaces only the matching `logo_surface` material. Its material blends the PNG alpha over the original car paint or glass. It hides the slot's `availability_marker` meshes only after the image loads, retaining the previous ad while a replacement downloads.

`GET /api/livery` returns the same uncached manifest as `/api/auction`: revision, current placements keyed by slot ID, immutable texture URLs, and recent history. An external renderer can consume this manifest without re-exporting the GLB. Integrating it into CARLA's native vehicle textures is separate work; this site does not claim that the simulator updates itself.

### Automatic social images

[Refresh sponsor social images](../../.github/workflows/social-images.yml) runs when a confirmed paid sponsorship changes the live wrap. The winning-bid transaction also records a durable image-update request, then starts the main-branch GitHub Actions workflow in the background. Unpaid checkouts, refunded losing bids and duplicate Stripe webhooks do not request another run. There is no recurring Actions schedule. The first request after deployment also queues a refresh if the published images do not match the deployed model/template, and the workflow remains available to run manually.

The job renders the same Three.js car, artwork fitting, fonts and confirmed textures as the website, with local headless Chromium on the runner. It freezes one livery snapshot and waits for the model, every texture and a completed frame. Both images are uploaded to R2 through `POST /api/social/publish` before the server makes their URLs current. A failed run keeps the previous pair visible. The existing Durable Object alarm retries a failed GitHub dispatch with backoff, and retries an accepted job after 15 minutes if it never publishes. Once the pair is published, its pending request is cleared and social-image retries stop. A newer sponsor or different deployed renderer rejects stale uploads. Retries never overwrite immutable URLs. Rendering and GitHub availability do not delay payment acknowledgement.

The website starts Actions using the production Worker secret `SOCIAL_IMAGES_GITHUB_TOKEN`. Use a dedicated fine-grained GitHub token restricted to `MarkUnthank/flyhard` with **Actions: read and write**; this is the permission required by GitHub's [workflow dispatch endpoint](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event). Keep its value out of the repository and set or rotate it through the approved production-secret configuration process. Without this credential the pending update remains saved and can still be published by running the workflow manually.

For the return request, Actions authenticates to the website with a short-lived GitHub OIDC token restricted to this repository's main-branch `social-images.yml` workflow. No Actions secret or Cloudflare browser binding is needed. The workflow can publish generated social images only; it does not deploy Worker code or commit assets. Website changes ship through the normal PR and Cloudflare Builds release process.

To render the live sponsors locally on your Mac, from `apps/website`:

```sh
npm ci
npm run social:render
```

The preview pair and revision receipt are written to ignored `artifacts/social/`. To publish locally instead, use `npm run social:update` with the existing `AUCTION_ADMIN_TOKEN` in the environment. That command requires a renderer fingerprint matching the deployed website, then publishes and reads back both image URLs. `-- --site http://localhost:8797` selects an isolated local API for testing; `-- --output /path/to/folder` changes the output location. `social:build` runs automatically before rendering, development, tests, typechecking and the Next/OpenNext build. It fingerprints the renderer bundle, model, fonts, capture code and dependency lockfile.

Next's metadata reads the current published URLs on each request. Each completed wrap gets a distinct URL containing the renderer fingerprint and auction revision. The `/api/social/wide.jpg` and `/api/social/square.jpg` aliases, plus the former `/social/driving-fly-*-v*.jpg` URLs, resolve to the latest complete pair with `Cache-Control: no-store`. The original v4 cards remain the fallback until the first job succeeds. Generated revision URLs stay immutable and available for old links.

We can refresh our metadata and image URLs; we cannot revoke a copy already cached by a social platform. Platforms need to scrape the page again to discover new URLs, and existing posts may retain their original previews. For example, [LinkedIn's Post Inspector](https://www.linkedin.com/help/linkedin/answer/a6269011) refreshes previews for new posts only.

After configuring the trigger credential, the authorized PR merge and Cloudflare build, check `GET /api/social`: `triggerConfigured` should be true, `pending` should become false and `publishedRevision` should equal `revision`. Fetch both returned `images` and check the homepage's `og:image` and `twitter:image` tags with a crawler user agent. Failed runs expose their error in Actions; `social_workflow_dispatched` and `social_workflow_retry` identify dispatch attempts in Worker logs. A run using a checkout that does not match the deployed renderer fails safely and the pending update retries. No timer remains once the images are current.

The supporter leaderboard uses `highestBids`: the 50 highest published paid bids of all time, including outbid sponsors, ordered by paid amount, publication time, and bid ID. It shows eight compact rows per page, without logos, and preserves each purchase’s original website link. The ranking is independent of the 50 most recent events in `history`, so older high bids remain eligible. Complimentary credit affects current placement prices, but does not inflate this paid-bid history.

The main car opens in 3D View and rotates slowly until the visitor interacts. Reduced-motion preferences disable rotation. Reset returns to the perspective view without restarting rotation. Checkout frames the selected spot independently. The bid dialog suggests an amount at least $1 above the highest effective bid, with a one-click update. Complimentary credits affect current bid thresholds, but never paid history or the fundraising total; see [COMPLIMENTARY-CREDITS.md](COMPLIMENTARY-CREDITS.md).

## Verification

```sh
npm run typecheck
npm test
npm run build:worker
npm audit
```

The tests run the actual Worker and SQLite/R2 bindings in Miniflare. Stripe HTTP calls are isolated with an in-process fake provider; no tests can contact the real Stripe API. They cover upload privacy, malformed files, hostile origins, forged signatures, unpaid checkouts, competing payments that fail the $1 increment, duplicates, refunds, WebSocket delivery, and immutable artwork serving. Advertiser profiles are checked for message length, immutable checkout retries, private logo uploads, prevention of upload reuse, and publication of both images and the message.

To run the built OpenNext Worker locally without rebuilding:

```sh
npx wrangler dev --port 3001 --var SITE_URL:http://localhost:3001 --persist-to .wrangler/production-preview
```

On September 9, 2026, the supplied restricted test key completed two real Stripe sandbox Checkouts through the website: a $1 initial placement and a $2 replacement on `ad-01`. Both signed `checkout.session.completed` webhooks returned HTTP 200. An independent browser observed revisions 1 and 2 over WebSockets and loaded each new R2 texture without a page refresh; the next minimum became $3. No live payment was made. The local preview retains these clearly marked test purchases.

Desktop and mobile checks covered the larger car, focused checkout camera, immediate artwork preview, sticky mobile model, footer links, and no horizontal page overflow. The integration suite verifies the $1 increment before Checkout and again at publication, including automatic refunds for a paid bid that is now less than $1 above the winner.

A subsequent $3 sandbox purchase verified the editor: 70% scale, 18° rotation, and 64%/55% horizontal/vertical placement. The published R2 image matched the preview pixel for pixel, including fully transparent and semitransparent pixels. A second browser loaded revision 3 and the new texture without refreshing. The Worker integration suite also verifies alpha survives upload and publication. The replacement root `STRIPE_API_KEY` authenticated successfully as a live restricted key; local checkout continues to use `STRIPE_TEST_API_KEY`.

A $4 sandbox replacement verified the advertiser profile: a 102-character message, visible website, and an independent 480 × 240 logo thumbnail were published alongside the transformed car texture. The signed webhook returned HTTP 200; an already-open observer received revision 4 and showed the new profile and model texture without refreshing. The 11 integration tests, TypeScript check, and OpenNext production build passed. The local preview retains this sample profile and reports $10 total test payments; no live payment was made.

Browser-only auction fixtures verified the default camera on all five faces, the empty-auction fallback, tied bids, manual angle and OrbitControls overrides during live leader changes, and Reset returning to the latest leader. These fixtures did not change stored placements or create payments.

Vehicle attribution is retained at `/credits`; font licensing is included with the model. All fonts, model textures, and Draco decoders used by the site are self-hosted.

## Historic page-view counter

The hero displays Cloudflare Web Analytics page views next to the active browser
connection count. This is page views (including repeat views), not unique people.
The source is site `a9425d0f08934c0b919b4c5ff11fb5f7`, with known bots excluded,
starting September 9, 2026 UTC, the date tracking was enabled. The GraphQL `count`
is already sampling-adjusted, so it is not multiplied by the sampling interval.

Before merging this feature, store a dedicated Cloudflare token with account
Analytics Read access as the production Worker secret `CLOUDFLARE_ANALYTICS_TOKEN`.
Do not use an expiring Wrangler login token. Keep the PR in draft until this is
configured. Secret configuration does not authorize manually deploying Worker code.

Cloudflare cron runs every five minutes. It calls the auction object through its
private Worker binding; visitors cannot trigger a sync. Daily aggregates persist
in Durable Object SQLite. The current day and previous two days are replaced on
refresh to incorporate delayed data without double counting. Older days remain
stored after Cloudflare retention expires. A bounded catch-up processes up to four
seven-day batches per run; failures preserve the last successfully published total.
The counter stays hidden until the first complete backfill. Staging has no cron and
cannot sync production analytics. After the Git build deploys, verify the first cron
succeeds and `/api/auction` reports `totalViews` matching the stored daily sum.

Cloudflare figures can be sampled and omit blocked/missed beacons. They represent
recorded views since tracking began, not a guaranteed census of every visitor.
