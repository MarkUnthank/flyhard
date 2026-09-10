export interface Env {
  AUCTION: DurableObjectNamespace;
  ARTWORK: R2Bucket;
  ASSETS: Fetcher;
  SITE_URL: string;
  STRIPE_API_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
}
