const keyPrefix = "driving-fly-checkout:";

function isCheckoutSession(sessionId: string): boolean {
  return (
    sessionId.length <= 250 && /^cs_(test_|live_)?[A-Za-z0-9]+$/.test(sessionId)
  );
}

// Remember return credentials only on the customer's browser. Never put them
// in public auction data. Storage can be unavailable in private browsers.
export function savedCheckouts(): string[] {
  try {
    const sessions = new Set<string>();
    for (let index = 0; index < localStorage.length; index++) {
      const key = localStorage.key(index);
      if (!key?.startsWith(keyPrefix)) continue;
      const sessionId = key.slice(keyPrefix.length);
      if (isCheckoutSession(sessionId)) sessions.add(sessionId);
    }
    return [...sessions];
  } catch {
    return [];
  }
}
export function rememberCheckout(sessionId: string) {
  if (!isCheckoutSession(sessionId)) return;
  try {
    // Separate keys keep one tab's changes from overwriting another checkout.
    localStorage.setItem(`${keyPrefix}${sessionId}`, "1");
  } catch {
    /* The Stripe return URL still lets the customer finish. */
  }
}
export function forgetCheckout(sessionId: string) {
  if (!isCheckoutSession(sessionId)) return;
  try {
    localStorage.removeItem(`${keyPrefix}${sessionId}`);
  } catch {
    /* Completed sessions are harmless to re-check. */
  }
}
