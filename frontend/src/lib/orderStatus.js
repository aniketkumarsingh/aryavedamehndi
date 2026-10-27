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
  cod_with_courier: "Paid at delivery",
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

export const SHIPMENT_STATUS_LABELS = {
  booked: "Packed & handed to courier",
  picked_up: "Picked up",
  in_transit: "In transit",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  ndr: "Delivery attempt failed",
  rto: "Returning to us",
  rto_delivered: "Returned to us",
  cancelled: "Shipment cancelled",
};

export const RETURN_STATUS_LABELS = {
  requested: "Return requested — we'll reply within 2 working days",
  approved: "Return approved — pickup arranged",
  rejected: "Return not approved",
  received: "Received — refund on its way",
  refunded: "Refunded",
};

export const RETURN_REASONS = [
  ["damaged", "Arrived damaged"],
  ["wrong_item", "Wrong item sent"],
  ["not_as_described", "Not as described"],
  ["changed_mind", "Changed my mind"],
];

const HI_LABELS = {
  order: {
    pending: "भुगतान बाकी",
    confirmed: "पक्का — भेजने की तैयारी",
    shipped: "भेज दिया गया",
    delivered: "डिलीवर हो गया",
    cancelled: "रद्द",
    returned: "हमारे पास वापस आ गया",
  },
  payment: {
    unpaid: "अभी भुगतान नहीं हुआ",
    paid: "ऑनलाइन भुगतान हो गया",
    cod_due: "कैश ऑन डिलीवरी — डिलीवरी पर भुगतान",
    cod_with_courier: "डिलीवरी पर भुगतान हो गया",
    cod_collected: "डिलीवरी पर भुगतान हो गया",
    refund_pending: "रिफ़ंड जारी है",
    partially_refunded: "आंशिक रिफ़ंड",
    refunded: "रिफ़ंड हो गया",
    void: "कोई भुगतान नहीं लिया गया",
  },
  refund: { pending: "शुरू हो रहा है", submitted: "आपके बैंक के पास", processed: "रिफ़ंड हो गया", failed: "देरी — हमारी टीम देख रही है" },
  shipment: {
    booked: "पैक करके कूरियर को सौंपा",
    picked_up: "कूरियर ने ले लिया",
    in_transit: "रास्ते में",
    out_for_delivery: "डिलीवरी के लिए निकला",
    delivered: "डिलीवर हो गया",
    ndr: "डिलीवरी की कोशिश नाकाम",
    rto: "हमारे पास लौट रहा है",
    rto_delivered: "हमारे पास लौट आया",
    cancelled: "शिपमेंट रद्द",
  },
  return: {
    requested: "वापसी का अनुरोध — हम 2 कार्यदिवस में जवाब देंगे",
    approved: "वापसी मंज़ूर — पिकअप तय",
    rejected: "वापसी मंज़ूर नहीं हुई",
    received: "मिल गया — रिफ़ंड आ रहा है",
    refunded: "रिफ़ंड हो गया",
  },
  reason: { damaged: "ख़राब हालत में पहुँचा", wrong_item: "ग़लत सामान आया", not_as_described: "जैसा बताया था वैसा नहीं", changed_mind: "मन बदल गया" },
};

const EN_LABELS = {
  order: ORDER_STATUS_LABELS,
  payment: PAYMENT_STATUS_LABELS,
  refund: REFUND_STATUS_LABELS,
  shipment: SHIPMENT_STATUS_LABELS,
  return: RETURN_STATUS_LABELS,
  reason: Object.fromEntries(RETURN_REASONS),
};

/** A status in the visitor's language, e.g. statusLabel("shipment", "in_transit", "hi"). */
export function statusLabel(kind, key, lang = "en") {
  return (lang === "hi" && HI_LABELS[kind]?.[key]) || EN_LABELS[kind]?.[key] || key;
}

// Steps of the progress bar for an order that isn't cancelled.
export const ORDER_STEPS = ["confirmed", "shipped", "delivered"];

export const canCancel = (order) => order.status === "pending" || order.status === "confirmed";
export const hasDocument = (order) => ["confirmed", "shipped", "delivered"].includes(order.status) || Boolean(order.invoice_number);

/** One short label for lists: the order status, or the refund state of a
 * cancelled/refunded order. */
export function orderSummaryLabel(order, lang = "en") {
  if (["cancelled", "returned"].includes(order.status) && ["refund_pending", "refunded", "partially_refunded"].includes(order.payment_status)) {
    return `${statusLabel("order", order.status, lang)} · ${statusLabel("payment", order.payment_status, lang)}`;
  }
  return statusLabel("order", order.status, lang);
}
