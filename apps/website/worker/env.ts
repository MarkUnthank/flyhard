export interface Env {
  AUCTION: DurableObjectNamespace;
  ARTWORK: R2Bucket;
  ASSETS: Fetcher;
  SITE_URL: string;
  EMAIL?: SendEmail;
  OUTBID_EMAIL_FROM?: string;
  /** Required for test-mode Stripe: all test mail is redirected here. */
  OUTBID_EMAIL_TEST_TO?: string;
  STRIPE_API_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
}
