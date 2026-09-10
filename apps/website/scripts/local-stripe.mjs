import { existsSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { parseEnv } from "node:util";
const localPath = new URL("../.dev.vars", import.meta.url);
const rootPath = new URL("../../../.env", import.meta.url);
export function localStripe() {
  const root = existsSync(rootPath)
    ? parseEnv(readFileSync(rootPath, "utf8"))
    : {};
  const local = existsSync(localPath)
    ? parseEnv(readFileSync(localPath, "utf8"))
    : {};
  const testKey = root.STRIPE_TEST_API_KEY;
  if (testKey) {
    if (!/^(sk|rk)_test_/.test(testKey))
      throw new Error(
        "STRIPE_TEST_API_KEY must be a Stripe test secret or restricted key.",
      );
    if (local.STRIPE_API_KEY !== testKey) delete local.STRIPE_WEBHOOK_SECRET;
    local.STRIPE_API_KEY = testKey;
    saveLocalStripe(local);
  }
  return local;
}
export function saveLocalStripe(values) {
  const temporary = new URL("../.dev.vars.tmp", import.meta.url);
  writeFileSync(
    temporary,
    Object.entries(values)
      .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
      .join("\n") + "\n",
    { mode: 0o600 },
  );
  renameSync(temporary, localPath);
}

export function stripeListenerKey() {
  const root = existsSync(rootPath)
    ? parseEnv(readFileSync(rootPath, "utf8"))
    : {};
  return root.STRIPE_CLI_API_KEY || localStripe().STRIPE_API_KEY;
}
