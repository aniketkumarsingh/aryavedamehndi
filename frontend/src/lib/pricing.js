// Pricing copy shared by every way of ordering (booking, own design, bulk
// event) so the site makes one promise everywhere. The rules themselves
// live in backend/app/services/pricing.py - keep the wording true to them.
import { OCCASIONS, formatPriceRange } from "./designs.js";

// Bulk-only events first, then the catalog occasions. Keys match
// backend/app/schemas/bulk_order.py BULK_OCCASIONS.
export const BULK_OCCASIONS = [
  { key: "mehndi-ceremony", label: "Mehndi Ceremony" },
  ...OCCASIONS.filter((o) => o.key !== "everyday"),
  { key: "society-event", label: "Society / Community Event" },
  { key: "corporate", label: "Corporate Event" },
  { key: "other", label: "Something else" },
];

export function bulkOccasionLabel(key) {
  return BULK_OCCASIONS.find((o) => o.key === key)?.label || key;
}

export const BULK_STATUS_LABELS = {
  requested: "Waiting for our quote",
  quoted: "Quote ready",
  confirmed: "Confirmed",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const DEPOSIT_LABELS = {
  not_required: "No deposit needed",
  pending: "Deposit due",
  paid: "Deposit paid",
  refund_pending: "Deposit refund in progress",
  refunded: "Deposit refunded",
  forfeited: "Deposit forfeited",
};

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
export const formatInr = (n) => `₹${inr.format(n)}`;

/** "10% of each person's price" / "₹49 per person" - from GET /pricing/policy. */
export function feeLabel(policy) {
  if (!policy) return "a small platform fee per person";
  return policy.platform_fee_mode === "flat"
    ? `${formatInr(policy.platform_fee_flat)} per person`
    : `${policy.platform_fee_percent}% of each person's price`;
}

/** The promises, in order. `policy` from GET /pricing/policy (may be null while loading). */
export function pricePromises(policy) {
  return [
    {
      title: "One price, however you order",
      body: "Booking for yourself, bringing your own design, or ordering for a whole event - every person is priced from the same package or design range. No custom-design surcharge, no bulk markup.",
    },
    {
      title: "Transparent platform fee",
      body: `Our fee is ${feeLabel(policy)}, shown separately before you pay anything.`,
    },
    {
      title: "Deposit that protects both sides",
      body: "Some packages need a small per-person deposit to secure your artist. It's refunded if you cancel before the artist heads out (for events, 24 hours or more before the start).",
    },
  ];
}

/** Sums EstimateOut into the two lines every order page shows. */
export function estimateSummary(est) {
  if (!est) return null;
  return {
    subtotal: formatPriceRange(est.subtotal_min, est.subtotal_max),
    fee: formatPriceRange(est.platform_fee_min, est.platform_fee_max),
    total: formatPriceRange(est.total_min, est.total_max),
    deposit: est.advance_amount > 0 ? formatInr(est.advance_amount) : null,
  };
}
