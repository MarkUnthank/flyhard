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

## Historic request counter

The hero displays Cloudflare zone HTTP request totals next to the active browser
connection count. Requests include page loads, assets, API polling, repeat requests,
and bot traffic. The label is “total requests”, not views or unique visitors.
The source is the site's zone HTTP analytics, starting September 9, 2026 UTC,
when the domain was added to Cloudflare. Use `httpRequests1dGroups.sum.requests`.

The encrypted production Worker secret `CLOUDFLARE_ANALYTICS_TOKEN` needs Zone
Analytics Read permission for this zone. It must never be committed or sent to
browsers. The previous Web Analytics account-only permission must be replaced
before releasing this change. Keep the PR in draft until credentials are configured.

Cloudflare cron runs every five minutes and invokes the auction object through
its private Worker binding. Daily aggregates persist in Durable Object SQLite;
refreshes replace the current and previous two days without double counting.
Older totals survive analytics retention. Catch-up is bounded to four seven-day
batches per run, preserving the last complete total on failure. The new counter
uses separate storage from the previous page-view metric; it never adds page
views to requests. It stays hidden until the first complete backfill. Staging
cannot sync production analytics.

After the Git-based release, verify the first successful cron and check
`/api/auction.totalRequests` against Cloudflare's zone request totals. Analytics
processing and the five-minute schedule mean this is not a per-request live ticker.
