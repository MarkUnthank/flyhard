import { z } from "zod";

export const WRAP_START_PRICE = 1_000_000;
export const WRAP_PRICE_STEP = 100;
export const WRAP_VIDEOS = 2;
export type CustomWrapSnapshot = {
  amount: number;
  soldCount: number;
  totalRaised: number;
  checkoutEnabled: boolean;
};
export const emptyCustomWrap: CustomWrapSnapshot = {
  amount: WRAP_START_PRICE,
  soldCount: 0,
  totalRaised: 0,
  checkoutEnabled: false,
};
export const wrapCheckoutSchema = z.object({
  requestId: z.uuid(),
  amount: z.number().int().min(WRAP_START_PRICE).max(99_999_999),
  acceptedTerms: z.literal(true),
});
