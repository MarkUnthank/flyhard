# Outbid notifications

Cloudflare Email Service sends a transactional email when a confirmed payment replaces a published ad. The sender is **The Driving Fly <mark@reallynice.company>**, so replies reach Mark's existing mailbox. The email identifies the displaced placement, the replacement bid, and the current minimum to bid again. Its `?spot=ad-XX` link opens that spot's model preview and bid form with the latest auction price.

## Payment and delivery behavior

The ownership change and an `outbid_emails` row are committed in the same SQLite transaction. The old bid ID is the notification's unique key, so repeat Stripe webhooks and checkout-return confirmation cannot enqueue it twice. Unpaid checkouts and paid bids refunded before publication never produce outbid mail.

Confirmed Stripe Checkout supplies `customer_details.email` (falling back to `customer_email`). It is stored in the private `bids.buyer_email` column. For sponsors bought before this feature, the Worker retrieves and validates their original paid Checkout session when they are first outbid. It does not backfill notifications for historical outbids. Public snapshots, WebSocket messages, livery exports and artwork responses exclude email addresses.

The Worker suppresses a notification when the same email raises its own bid, or has already regained that spot before the queued email is sent. Email processing does not block payment publication. A Durable Object alarm retries temporary Stripe/email failures with exponential backoff, capped at one hour. Pending work survives Worker restarts; a constructor check restores its alarm when the object starts with email sending configured.

A successful provider response stores the Cloudflare message ID and marks the outbox row `sent`. This means **accepted for delivery**, not confirmed inbox placement. Cloudflare handles onward SMTP delivery and suppresses bounced/complaining recipients. A missing Checkout email or suppressed recipient is retained as `failed` for operator attention.

Cloudflare's send binding does not expose an idempotency key. The durable outbox prevents normal duplicate sends, but a crash after Cloudflare accepts a message and before SQLite records the result can cause a duplicate on retry. Each message carries a stable `X-Outbid-Notification` header to correlate such attempts.

## Configuration

Production and staging have an `EMAIL` send binding restricted to the sender above, plus `OUTBID_EMAIL_FROM` in `wrangler.jsonc`. Local configuration uses the same sender with simulated delivery. Custom-wrap buyer confirmations and operator alerts also use this sender.

The sender domain `reallynice.company` must be enabled in Cloudflare Email Service before releasing this configuration. Cloudflare uses `cf-bounce.reallynice.company` for return-path MX and SPF records and `cf-bounce._domainkey.reallynice.company` for DKIM. Keep the existing Google Workspace root MX/SPF and DMARC policy intact. The domain uses strict DMARC alignment, so Cloudflare's DKIM signature must use `d=reallynice.company`; the bounce subdomain's SPF alone does not satisfy strict alignment. No additional email API key is needed. See [Cloudflare's domain configuration guide](https://developers.cloudflare.com/email-service/configuration/domains/).

For Stripe test mode, sending requires a private `OUTBID_EMAIL_TEST_TO` secret. **Every sandbox notification goes to that test address**, with `[TEST]` in the subject and an explanation that no real payment or production replacement occurred. The original bidder email is still used to check ownership, but never used as a sandbox destination. Without the test recipient, queued sandbox mail remains unsent.

```sh
npx wrangler secret put OUTBID_EMAIL_TEST_TO --env staging
```

Set that secret only for a consenting test recipient. Local development has no outbound email binding and sends no real mail. Integration tests use a fake binding and isolated Stripe responses; they cannot access the real providers.

## Operations

In Cloudflare, open **Compute → Email Service → Email Sending → Activity log**. Search the message ID from the Worker log or `outbid_emails.message_id` to inspect acceptance, delivery, bounce status and message preview. `sent` and `delivered` are separate provider events.

Worker logs contain notification IDs and error codes, never recipient addresses or raw provider errors:

- `Outbid email accepted`: provider accepted the message.
- `Outbid email will retry`: queued work remains pending.
- `Outbid email needs attention`: no usable Checkout email or a suppressed recipient.

Use the auction's private Durable Object SQLite data explorer to inspect the queue, without exporting email addresses:

```sql
SELECT previous_bid_id, replacement_bid_id, status, attempts,
       datetime(created_at / 1000, 'unixepoch') AS created,
       datetime(next_attempt_at / 1000, 'unixepoch') AS next_attempt,
       message_id, last_error
FROM outbid_emails
ORDER BY created_at DESC
LIMIT 50;
```

Correct sender/authentication or Stripe access problems and pending jobs resume automatically. Investigate missing recipient data or bounce reports individually; do not bulk resend failed jobs or remove Cloudflare suppressions without resolving the cause. This feature adds no public admin or test-send endpoint.
