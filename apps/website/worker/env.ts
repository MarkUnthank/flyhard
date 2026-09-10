export interface Env extends Pick<
  CloudflareBindings,
  "AUCTION" | "ARTWORK" | "ASSETS" | "SITE_URL"
> {
  EMAIL?: SendEmail;
  OUTBID_EMAIL_FROM?: string;
  /** Required for test-mode Stripe: all test mail is redirected here. */
  OUTBID_EMAIL_TEST_TO?: string;
  CUSTOM_WRAP_EMAIL_TO?: string;
  CUSTOM_WRAP_EMAIL_TEST_TO?: string;
  STRIPE_API_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  AUCTION_ADMIN_TOKEN?: string;
}
