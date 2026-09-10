import inventory from "./ad-spaces.json";
import { z } from "zod";
import { emptyCustomWrap, type CustomWrapSnapshot } from "./custom-wrap";

export const slots = inventory.slots;
export const modelUrl = inventory.model_url;
export const artworkCrops: Record<string, number[]> = inventory.artwork_crops;
export type Slot = (typeof slots)[number];
export type Placement = {
  id: string;
  slotId: string;
  brand: string;
  message: string;
  url: string;
  amount: number;
  paidAmount?: number;
  complimentaryCredit?: number;
  textureUrl: string;
  logoUrl: string;
  publishedAt: number;
};
// Stable geometry IDs: keep paid placements, then fill the remaining inventory
// with prominent surfaces. A payment already in flight can never erase a sponsor.
const preferredSlotIds = inventory.active_slot_ids;
export const INVENTORY_SIZE = preferredSlotIds.length;
export function activeSlots(placements: Record<string, Placement>) {
  const sold = slots.filter((slot) => placements[slot.id]);
  const remaining = preferredSlotIds
    .filter((id) => !placements[id])
    .slice(0, Math.max(0, INVENTORY_SIZE - sold.length));
  const ids = new Set([...sold.map((slot) => slot.id), ...remaining]);
  return slots.filter((slot) => ids.has(slot.id));
}
export function compareSlots(
  a: Slot,
  b: Slot,
  placements: Record<string, Placement>,
  byPrice = false,
) {
  return (
    Number(Boolean(placements[b.id])) - Number(Boolean(placements[a.id])) ||
    (byPrice
      ? (placements[b.id]?.amount || 0) - (placements[a.id]?.amount || 0)
      : 0) ||
    a.position_order - b.position_order
  );
}
export function rankPlacements(placements: Record<string, Placement>) {
  return Object.values(placements).sort(
    (a, b) =>
      b.amount - a.amount ||
      a.publishedAt - b.publishedAt ||
      a.slotId.localeCompare(b.slotId),
  );
}
export type AuctionSnapshot = {
  customWrap: CustomWrapSnapshot;
  activeSlotIds: string[];
  revision: number;
  placements: Record<string, Placement>;
  history: Placement[];
  highestBids: Placement[];
  totalRaised: number;
  totalPurchases: number;
  online: number;
  paymentsEnabled: boolean;
  paymentMode: "live" | "test" | "unavailable";
};
export const emptySnapshot: AuctionSnapshot = {
  customWrap: emptyCustomWrap,
  activeSlotIds: activeSlots({}).map((slot) => slot.id),
  revision: 0,
  placements: {},
  history: [],
  highestBids: [],
  totalRaised: 0,
  totalPurchases: 0,
  online: 0,
  paymentsEnabled: false,
  paymentMode: "unavailable",
};
export const money = (cents: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cents % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(cents / 100);
export const minimumBid = (current = 0) => (current ? current + 100 : 100);
export const dollarsToCents = (value: string) => {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
  const [whole, decimal = ""] = value.split(".");
  const cents = Number(whole) * 100 + Number(decimal.padEnd(2, "0"));
  return Number.isSafeInteger(cents) ? cents : null;
};
export const bidSchema = z.object({
  requestId: z.uuid(),
  slotId: z
    .string()
    .refine(
      (id) => slots.some((slot) => slot.id === id),
      "Choose a valid spot.",
    ),
  amount: z.number().int().min(100).max(99_999_999),
  brand: z.string().trim().min(1).max(60),
  message: z.string().trim().max(140),
  url: z
    .url()
    .max(500)
    .refine((value) => {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password;
    }, "Use an https:// website address."),
  artworkToken: z.uuid(),
  logoToken: z.uuid(),
  acceptedTerms: z.literal(true),
});
export type BidInput = z.infer<typeof bidSchema>;
