import { describe, expect, it } from "vitest";
import {
  checkoutEmail,
  emailErrorCode,
  outbidEmail,
} from "../worker/outbid-email";

describe("outbid email content", () => {
  it("escapes advertiser text, uses a site-owned link, and formats cents accurately", () => {
    const result = outbidEmail({
      siteUrl: "https://example.test",
      slotId: "ad-54",
      slotName: "Rear window",
      brand: '<a href="https://evil.test">hey</a>',
      previousAmount: 100,
      replacementAmount: 223,
      currentAmount: 500,
      test: false,
    });
    expect(result.html).not.toContain('<a href="https://evil.test">');
    expect(result.html).toContain("&lt;a href=&quot;");
    expect(result.html).toContain('href="https://example.test/?spot=ad-54"');
    expect(result.text).toContain("confirmed $2.23 bid");
    expect(result.text).toContain("starts at $6 USD");
    expect(result.html).not.toContain("<img");
  });
  it("accepts only Stripe email fields, rejects header injection and excludes addresses from error logs", () => {
    expect(
      checkoutEmail({
        customer_details: { email: "owner@example.test" },
        customer_email: "other@example.test",
      }),
    ).toBe("owner@example.test");
    expect(checkoutEmail({ customer_email: "fallback@example.test" })).toBe(
      "fallback@example.test",
    );
    expect(
      checkoutEmail({
        customer_email: "owner@example.test\nBcc:someone@example.test",
      }),
    ).toBeNull();
    expect(checkoutEmail({})).toBeNull();
    expect(emailErrorCode({ code: "E_RATE_LIMIT_EXCEEDED" })).toBe(
      "E_RATE_LIMIT_EXCEEDED",
    );
    expect(emailErrorCode(new Error("owner@example.test is unavailable"))).toBe(
      "E_NOTIFICATION_RETRY",
    );
  });
});
