# Complimentary sponsor credits

`POST /api/admin/credits` accepts an owner-authorized credit in integer USD cents.
It requires the `AUCTION_ADMIN_TOKEN` Worker secret as a bearer token. This token
must never appear in client code or public environment variables.

Use `node scripts/grant-credit.mjs --bid-id <current-bid-uuid> --request-id <unique-uuid> --expected-amount 200 --credit 400 --reason "Owner-authorized complimentary boost"` with `AUCTION_ADMIN_TOKEN` in the process environment. Reuse the request ID when retrying an uncertain response. A conflicting retry or stale current placement is rejected.

Each grant is stored in `complimentary_credits`, with its request ID, bid ID,
amount, reason, and timestamp. The original bid/payment is never updated.
Current placements expose `amount` (paid plus credit), `paidAmount`, and
`complimentaryCredit`. Ranking, checkout minimums, and settlement use the effective
amount. History, Stripe verification/refunds, revenue, and purchase counts use
the original paid amount. Credits stay attached to that bid and do not transfer
to its replacement. Every new grant advances the live revision and broadcasts it.

A $2 paid placement with $4 credit ranks at $6 and requires $7 to replace.
This does not create a Stripe charge or a new purchase. All ordinary deployments
include the credit support through `worker/auction.ts`; preserve the admin secret.
