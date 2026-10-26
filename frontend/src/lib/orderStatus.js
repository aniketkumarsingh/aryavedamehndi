// Customer-facing wording for a shop order's two states: where the parcel
// is (status) and where the money is (payment_status). Mirrors the backend
// state machines in app/services/shop_orders.py.

export const ORDER_STATUS_LABELS = {
  pending: "Awaiting payment",
  confirmed: "Confirmed — preparing to ship",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
  returned: "Returned to us",
};

export const PAYMENT_STATUS_LABELS = {
  unpaid: "Not paid yet",
  paid: "Paid online",
  cod_due: "Cash on Delivery — pay at delivery",
  cod_collected: "Paid at delivery",
  refund_pending: "Refund in progress",
  partially_refunded: "Partly refunded",
  refunded: "Refunded",
  void: "No payment taken",
};

export const REFUND_STATUS_LABELS = {
  pending: "Starting",
  submitted: "With your bank",
  processed: "Refunded",
  failed: "Delayed — our team is on it",
};

// Steps of the progress bar for an order that isn't cancelled.
export const ORDER_STEPS = ["confirmed", "shipped", "delivered"];

export const canCancel = (order) => order.status === "pending" || order.status === "confirmed";
export const hasDocument = (order) => ["confirmed", "shipped", "delivered"].includes(order.status) || Boolean(order.invoice_number);

/** One short label for lists: the order status, or the refund state of a
 * cancelled/refunded order. */
export function orderSummaryLabel(order) {
  if (["cancelled", "returned"].includes(order.status) && ["refund_pending", "refunded", "partially_refunded"].includes(order.payment_status)) {
    return `${ORDER_STATUS_LABELS[order.status]} · ${PAYMENT_STATUS_LABELS[order.payment_status]}`;
  }
  return ORDER_STATUS_LABELS[order.status] || order.status;
}
