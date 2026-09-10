import { parseArgs } from "node:util";

// Reuse the same request ID if the response is interrupted or uncertain.
const { values } = parseArgs({
  options: {
    site: { type: "string", default: "https://thedrivingfly.com" },
    "bid-id": { type: "string" },
    "request-id": { type: "string" },
    "expected-amount": { type: "string" },
    credit: { type: "string" },
    reason: { type: "string" },
  },
});
if (!process.env.AUCTION_ADMIN_TOKEN)
  throw new Error("Set AUCTION_ADMIN_TOKEN before granting credit.");
for (const name of [
  "bid-id",
  "request-id",
  "expected-amount",
  "credit",
  "reason",
]) {
  if (!values[name])
    throw new Error(`Missing --${name}. Amounts are integer cents.`);
}
const response = await fetch(new URL("/api/admin/credits", values.site), {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.AUCTION_ADMIN_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    requestId: values["request-id"],
    bidId: values["bid-id"],
    expectedAmount: Number(values["expected-amount"]),
    credit: Number(values.credit),
    reason: values.reason,
  }),
});
const result = await response.json();
if (!response.ok) throw new Error(`${response.status}: ${result.error}`);
console.log(
  JSON.stringify(
    {
      revision: result.revision,
      totalRaised: result.totalRaised,
      placement: Object.values(result.placements).find(
        (p) => p.id === values["bid-id"],
      ),
    },
    null,
    2,
  ),
);
