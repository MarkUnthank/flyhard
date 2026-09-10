const key = "driving-fly-checkouts";

// Remember return credentials only on the customer's browser. Never put them
// in public auction data. Storage can be unavailable in private browsers.
export function savedCheckouts(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value)
      ? value.filter(
          (id): id is string =>
            typeof id === "string" &&
            /^cs_(test_|live_)?[A-Za-z0-9]+$/.test(id) &&
            id.length <= 250,
        )
      : [];
  } catch {
    return [];
  }
}
export function rememberCheckout(sessionId: string) {
  try {
    localStorage.setItem(
      key,
      JSON.stringify([...new Set([sessionId, ...savedCheckouts()])]),
    );
  } catch {
    /* The Stripe return URL still lets the customer finish. */
  }
}
export function forgetCheckout(sessionId: string) {
  try {
    localStorage.setItem(
      key,
      JSON.stringify(savedCheckouts().filter((id) => id !== sessionId)),
    );
  } catch {
    /* Completed sessions are harmless to re-check. */
  }
}
