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

export function addToCart(product, quantity = 1) {
  const items = getCart();
  const existing = items.find((i) => i.product_id === product.id);
  if (existing) {
    existing.quantity = Math.min(existing.quantity + quantity, 50);
  } else {
    items.push({
      product_id: product.id,
      name: product.name,
      price: product.price,
      image_url: (product.image_urls || "").split(",").filter(Boolean)[0] || null,
      quantity: Math.min(quantity, 50),
    });
  }
  saveCart(items);
  return items;
}

export function updateCartQuantity(productId, quantity) {
  let items = getCart();
  if (quantity <= 0) {
    items = items.filter((i) => i.product_id !== productId);
  } else {
    const existing = items.find((i) => i.product_id === productId);
    if (existing) existing.quantity = Math.min(quantity, 50);
  }
  saveCart(items);
  return items;
}

export function removeFromCart(productId) {
  const items = getCart().filter((i) => i.product_id !== productId);
  saveCart(items);
  return items;
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
