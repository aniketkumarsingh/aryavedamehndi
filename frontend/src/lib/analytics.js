// Marketing analytics: Google Analytics 4 (also feeds Google Ads) and the
// Meta Pixel (Facebook/Instagram ads). Nothing loads unless its ID is set
// in the environment AND the visitor has accepted analytics cookies in the
// consent banner (India's DPDP Act needs consent for this kind of tracking).

export const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "";
export const META_PIXEL_ID = process.env.NEXT_PUBLIC_META_PIXEL_ID || "";
export const analyticsConfigured = Boolean(GA_ID || META_PIXEL_ID);

const CONSENT_KEY = "aryaveda_consent";
export const CONSENT_EVENT = "aryaveda-consent-changed";

export function getConsent() {
  try {
    return localStorage.getItem(CONSENT_KEY); // "granted" | "denied" | null
  } catch {
    return null;
  }
}

export function setConsent(value) {
  try {
    localStorage.setItem(CONSENT_KEY, value);
  } catch {
    /* storage blocked - the choice just won't be remembered */
  }
  window.dispatchEvent(new Event(CONSENT_EVENT));
}

// GA4 recommended event names -> Meta standard events.
const META_EVENTS = {
  view_item: "ViewContent",
  add_to_cart: "AddToCart",
  begin_checkout: "InitiateCheckout",
  purchase: "Purchase",
  sign_up: "CompleteRegistration",
  generate_lead: "Lead",
};

// value/currency/items follow GA4's ecommerce shape; Meta gets the same value.
export function track(name, params = {}) {
  if (typeof window === "undefined" || getConsent() !== "granted") return;
  if (window.gtag) window.gtag("event", name, params);
  if (window.fbq && META_EVENTS[name]) {
    // A purchase's event id is the order id - the server sends the same one
    // (Conversions API), so Meta counts the purchase once.
    const options = params.transaction_id ? { eventID: String(params.transaction_id) } : undefined;
    window.fbq(
      "track",
      META_EVENTS[name],
      {
        value: params.value,
        currency: params.currency || "INR",
        content_ids: (params.items || []).map((i) => i.item_id),
        content_type: "product",
      },
      options
    );
  }
}

export function cartItemsForAnalytics(items) {
  return items.map((i) => ({
    item_id: i.variant_id || i.product_id,
    item_name: i.name,
    item_variant: i.variant_label || undefined,
    price: i.price,
    quantity: i.quantity,
  }));
}
