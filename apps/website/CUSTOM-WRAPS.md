# Custom wraps

The homepage sells a full custom livery for the simulated Mini and **two released project videos** featuring it. The first order is $10,000 USD, charged in full through Stripe Checkout with automatic capture. Each confirmed order opens the next price immediately: $10,001, $10,002, and so on. Production follows purchase and is arranged with the buyer by email, in purchase order.

The package is separate from the spot auction. Buying it does not replace existing website sponsors; it adds the paid amount to the experiment's total funding. There is no automatic claim that design work or the videos have been delivered.

## Purchase notifications

Production uses `CUSTOM_WRAP_EMAIL_TO=mark@reallynice.company`. Messages come from the existing `OUTBID_EMAIL_FROM` sender through the `EMAIL` binding. Each message contains the order number, amount paid, buyer email, brand/project name, deliverables, and a Stripe payment link. Contact the buyer to get their creative brief and start production.

Checkout is disabled unless Stripe credentials, the webhook signing secret, sender, email binding, and recipient are configured. Test-mode purchases require `CUSTOM_WRAP_EMAIL_TEST_TO` and never fall back to the production recipient. Test messages are marked `[TEST]` and explicitly say not to begin production. Local `wrangler dev` simulates email delivery by default.

## Payment integrity and recovery

- The server fixes the price before creating Checkout and rejects stale browser prices. Retrying the same request reuses the same order and Stripe idempotency key.
- Signed webhooks and the checkout return both retrieve authoritative Stripe state. Payment status, amount, currency, mode, session, payment intent, and order identity must match.
- A synchronous SQL transaction accepts one purchase at each price, assigns the purchase sequence, increments the public revision, and queues the notification together.
- If two buyers pay the same price, one order is accepted. The other receives an automatic full refund and does not change the price or trigger a production email. Stripe never charges the extra dollar without a new checkout. The terms and Checkout disclose this race.
- The existing Durable Object alarm reconciles missed payments, expired sessions, refunds and email retries. A failed email cannot lose the paid order or undo its price increase. Pending/failed refunds stay pending until Stripe confirms success.
- Normal duplicate webhooks and simultaneous confirmations cannot send duplicate alerts. Email delivery is at least once: if the provider accepts a message immediately before the Worker loses its response, a retry can produce a duplicate. Use the stable order number to identify the same job.
- Operational records live in `wrap_orders` in the existing Auction Durable Object. Useful columns are `status`, `sale_number`, `paid_at`, `notification_status`, `notification_attempts`, `notification_error`, `notification_message_id`, and `refund_id`. A paid order is awaiting human production; it is not marked as a delivered wrap.
- Customer details and payment identifiers are excluded from all public snapshots. Manual cancellations, disputes, delivery and any operator refunds are handled through the existing payment/support process.

## Local verification

Run `npm run check` to run the type check, integration tests and local Worker build. The integration suite covers exact pricing/capture/deliverables, duplicate and concurrent payments, malformed and mismatched requests, private customer data, missed webhooks, restart recovery, failed emails, pending refunds and sandbox isolation.

For isolated previews alongside another local site, set `AUCTION_API_URL` for both Next.js and the Stripe listener. Run Wrangler on that port with `SITE_URL` matching your chosen Next.js origin, for example:

```sh
npx wrangler dev -c wrangler.dev.jsonc --port 8796 --var SITE_URL:http://localhost:3126
AUCTION_API_URL=http://127.0.0.1:8796 npx next dev --port 3126
AUCTION_API_URL=http://127.0.0.1:8796 npm run stripe:listen
```

Production release follows the repository's PR and Cloudflare Builds workflow. Do not deploy a local checkout to production.

## Verified on September 10, 2026

Two real Stripe sandbox Checkout purchases charged $10,000 and $10,001 with automatic capture. Signed webhooks returned successfully, both checkout returns confirmed the orders, and an already-open browser updated to $10,002 without a reload. The second order sent a real `[TEST]` alert through the Cloudflare email binding to the configured operator inbox; Gmail delivery and the two-video message were verified. All payment and order state stayed in isolated local/test storage. Local email was returned to simulated delivery afterward. No live payment or production deployment was performed.
