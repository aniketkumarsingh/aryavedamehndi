const CART_KEY = "aryaveda_cart";
export const CART_CHANGED_EVENT = "aryaveda-cart-changed";

function notifyCartChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CART_CHANGED_EVENT));
  }
}

export function getCart() {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CART_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveCart(items) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(items));
  } catch {
    /* private-browsing storage can throw - cart just won't persist */
  }
  notifyCartChanged();
}

// One cart line per product + pack size.
export function lineKey(item) {
  return `${item.product_id}:${item.variant_id || ""}`;
}

export function addToCart(product, quantity = 1, variant = null) {
  const items = getCart();
  const key = `${product.id}:${variant?.id || ""}`;
  const existing = items.find((i) => lineKey(i) === key);
  if (existing) {
    existing.quantity = Math.min(existing.quantity + quantity, 50);
  } else {
    items.push({
      product_id: product.id,
      variant_id: variant?.id || null,
      variant_label: variant?.label || null,
      name: product.name,
      price: variant ? variant.price : product.price,
      image_url: (product.image_urls || "").split(",").filter(Boolean)[0] || null,
      quantity: Math.min(quantity, 50),
    });
  }
  saveCart(items);
  return items;
}

export function updateCartQuantity(key, quantity) {
  let items = getCart();
  if (quantity <= 0) {
    items = items.filter((i) => lineKey(i) !== key);
  } else {
    const existing = items.find((i) => lineKey(i) === key);
    if (existing) existing.quantity = Math.min(quantity, 50);
  }
  saveCart(items);
  return items;
}

export function removeFromCart(key) {
  const items = getCart().filter((i) => lineKey(i) !== key);
  saveCart(items);
  return items;
}

/** Replaces the whole cart (used when merging a server-saved cart). */
export function replaceCart(items) {
  saveCart(items);
}

export function clearCart() {
  saveCart([]);
}

export function cartCount(items) {
  return items.reduce((sum, i) => sum + i.quantity, 0);
}

export function cartTotal(items) {
  return items.reduce((sum, i) => sum + i.price * i.quantity, 0);
}
