import { spawn } from "node:child_process";
import {
  localStripe,
  saveLocalStripe,
  stripeListenerKey,
} from "./local-stripe.mjs";
const values = localStripe();
if (!/^(sk|rk)_test_/.test(values.STRIPE_API_KEY ?? ""))
  throw new Error(
    "Set STRIPE_TEST_API_KEY in the repository root .env before starting the test listener.",
  );
const child = spawn(
  "stripe",
  [
    "listen",
    "--skip-update",
    "--events",
    "checkout.session.completed,checkout.session.async_payment_succeeded",
    "--forward-to",
    "http://localhost:8788/api/stripe/webhook",
  ],
  {
    env: { ...process.env, STRIPE_API_KEY: stripeListenerKey() },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let buffer = "";
function output(chunk) {
  buffer += String(chunk);
  const lines = buffer.split(/\r?\n/);
  buffer = lines.pop() ?? "";
  for (const line of lines) {
    const secret = line.match(/whsec_[a-zA-Z0-9]+/)?.[0];
    if (secret) {
      saveLocalStripe({ ...localStripe(), STRIPE_WEBHOOK_SECRET: secret });
      console.log(
        "Stripe test webhooks connected. Local signing secret saved; checkout is ready.",
      );
    } else
      console.log(
        line.replace(/(?:[rs]k)_(?:test|live)_[a-zA-Z0-9]+/g, "[REDACTED]"),
      );
  }
}
child.stdout.on("data", output);
child.stderr.on("data", output);
child.on("error", () => {
  console.error(
    "Install the Stripe CLI, then run npm run stripe:listen again.",
  );
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 0;
});
process.on("SIGINT", () => child.kill("SIGTERM"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
