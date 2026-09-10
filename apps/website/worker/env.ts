import type { Auction } from "./auction";

export interface Env extends Pick<CloudflareBindings, "ARTWORK" | "ASSETS" | "SITE_URL"> {
  AUCTION: DurableObjectNamespace<Auction>;
  CLOUDFLARE_ANALYTICS_TOKEN?: string;
  EMAIL?: SendEmail;
  OUTBID_EMAIL_FROM?: string;
  /** Required for test-mode Stripe: all test mail is redirected here. */
  OUTBID_EMAIL_TEST_TO?: string;
  CUSTOM_WRAP_EMAIL_TO?: string;
  CUSTOM_WRAP_EMAIL_TEST_TO?: string;
  STRIPE_API_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  AUCTION_ADMIN_TOKEN?: string;
  /** Repository-scoped credential with Actions: write, used only to dispatch the social workflow. */
  SOCIAL_IMAGES_GITHUB_TOKEN?: string;
}

declare global {
  interface CloudflareEnv extends CloudflareBindings {}
}
