# Custom wraps

The homepage sells a full custom livery for the simulated Mini and **two released project videos** featuring it. The first order is $10,000 USD, charged in full through Stripe Checkout with automatic capture. Each confirmed order opens the next price immediately: $10,001, $10,002, and so on. Production follows purchase and is arranged with the buyer by email, in purchase order.

The package is separate from the spot auction. Buying it does not replace existing website sponsors; it adds the paid amount to the experiment's total funding. There is no automatic claim that design work or the videos have been delivered.

## Purchase notifications

Production uses `CUSTOM_WRAP_EMAIL_TO=mark@reallynice.company`. Buyer confirmations and operator alerts come from **The Driving Fly <mark@reallynice.company>**, configured through `OUTBID_EMAIL_FROM` and the `EMAIL` binding. Replies reach Mark's existing mailbox. The operator alert contains the order number, amount paid, buyer email, brand/project name, deliverables, and a Stripe payment link. Sender authentication is documented in [OUTBID-NOTIFICATIONS.md](OUTBID-NOTIFICATIONS.md#configuration).

The buyer receives a separate welcome email at their verified Stripe Checkout email. It confirms their payment and two videos, asks them to [book a meeting with Mark ASAP](https://cal.com/mark-unthank/meeting), links the [Mini's paint texture on GitHub](https://github.com/MarkUnthank/flyhard/blob/main/apps/mini-livery/custom-wrap/M_Bodywork_Mini2021_d.png), and encourages them to vibe, sketch, or start designing before the call. Replies go to the operator. Both HTML and plain-text versions contain the links. The texture is extracted unchanged from the original packed Blender asset; the adjacent design guide includes attribution and the editable model.

Checkout is disabled unless Stripe credentials, the webhook signing secret, sender, email binding, and recipient are configured. Test-mode purchases require `CUSTOM_WRAP_EMAIL_TEST_TO`: both operator and buyer emails are redirected there, never to a checkout customer or the production recipient. Test messages are marked `[TEST]` and explicitly say not to book or begin production. Local `wrangler dev` simulates email delivery by default.

## Payment integrity and recovery

- The server fixes the price before creating Checkout and rejects stale browser prices. Retrying the same request reuses the same order and Stripe idempotency key.
- Signed webhooks and the checkout return both retrieve authoritative Stripe state. Payment status, amount, currency, mode, session, payment intent, and order identity must match.
- A synchronous SQL transaction accepts one purchase at each price, assigns the purchase sequence, increments the public revision, and queues both notifications together.
- If two buyers pay the same price, one order is accepted. The other receives an automatic full refund and does not change the price or trigger a production email. Stripe never charges the extra dollar without a new checkout. The terms and Checkout disclose this race.
- The existing Durable Object alarm reconciles missed payments, expired sessions, refunds and email retries. If the session-creation response was lost, recovery checks Stripe's paginated session list for the order's creation window and metadata, including after the idempotency-key retention period. A failed email cannot lose the paid order or undo its price increase. Pending/failed refunds stay pending until Stripe confirms success.
- Normal duplicate webhooks and simultaneous confirmations cannot send duplicate alerts. Each audience has independent delivery status and retries: failure to send a buyer email does not resend the operator alert or block its delivery, and vice versa. Email delivery is at least once: if the provider accepts a message immediately before the Worker loses its response, a retry can produce a duplicate. Use the stable order number to identify the same job.
- Operational records live in `wrap_orders` in the existing Auction Durable Object. Useful columns are `status`, `sale_number`, `paid_at`, and `refund_id`. Email jobs live in `wrap_notifications`, keyed by `order_id` and `audience` (`operator` or `buyer`), with `status`, `attempts`, `next_attempt_at`, `message_id`, and `error`. A paid order is awaiting human production; it is not marked as a delivered wrap.
- Customer details and payment identifiers are excluded from all public snapshots. Manual cancellations, disputes, delivery and any operator refunds are handled through the existing payment/support process.

## Local verification

Run `npm run check` to run the type check, integration tests and local Worker build. The integration suite covers exact pricing/capture/deliverables, duplicate and concurrent payments, malformed and mismatched requests, private customer data, missed webhooks, restart recovery, failed emails, pending refunds and sandbox isolation.

For isolated previews alongside another local site, set `AUCTION_API_URL` for both Next.js and the Stripe listener. Run Wrangler on that port with `SITE_URL` matching your chosen Next.js origin, for example:

```sh
npx wrangler dev -c wrangler.dev.jsonc --port 8796 --persist-to .wrangler/preview-8796 --var SITE_URL:http://localhost:3126
AUCTION_API_URL=http://127.0.0.1:8796 npx next dev --port 3126
AUCTION_API_URL=http://127.0.0.1:8796 npm run stripe:listen
```

Production release follows the repository's PR and Cloudflare Builds workflow. Do not deploy a local checkout to production.

## Verified on September 10, 2026

Two real Stripe sandbox Checkout purchases charged $10,000 and $10,001 with automatic capture. Signed webhooks returned successfully, both checkout returns confirmed the orders, and an already-open browser updated to $10,002 without a reload. The second order sent a real `[TEST]` alert through the Cloudflare email binding to the configured operator inbox; Gmail delivery and the two-video message were verified. All payment and order state stayed in isolated local/test storage. Local email was returned to simulated delivery afterward. No live payment or production deployment was performed.

A further $10,000 sandbox purchase in fresh local storage verified both independent emails. The buyer welcome and operator alert reached the operator's test inbox; the buyer email's HTML and plain-text booking and texture links, two-video deliverable, reply address, and test warning were read back from Gmail. The confirmation screen showed the booking instruction and the next price of $10,001. The texture and design guide ship in the same PR, so the email's `main` links become available when that PR is merged. The 46-test suite, type check, and production Worker build passed. Local email was returned to simulated delivery after this test.
