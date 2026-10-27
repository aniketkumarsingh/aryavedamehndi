import { useEffect, useRef } from "react";
import { AUTH_CHANGED_EVENT, api, getStoredUser } from "@/lib/api";
import { CART_CHANGED_EVENT, getCart, replaceCart } from "@/lib/cart";

const toServer = (items) => items.map((i) => ({ product_id: i.product_id, variant_id: i.variant_id || null, quantity: i.quantity }));

/** Keeps a logged-in shopper's cart on the server too, so it follows them
 * across devices and an abandoned cart can be followed up. On login the
 * server copy is merged into this browser's cart (larger quantity wins).
 * Renders nothing. */
export default function CartSync() {
  const timer = useRef(null);
  const merging = useRef(false);

  useEffect(() => {
    const isShopper = () => getStoredUser()?.role === "consumer";

    async function mergeFromServer() {
      if (!isShopper()) return;
      merging.current = true;
      try {
        const server = await api.get("/shop/cart");
        const local = getCart();
        const key = (i) => `${i.product_id}:${i.variant_id || ""}`;
        const byKey = Object.fromEntries(local.map((i) => [key(i), i]));
        const missing = [];
        for (const line of server.items || []) {
          const existing = byKey[key(line)];
          if (existing) existing.quantity = Math.max(existing.quantity, line.quantity);
          else missing.push(line);
        }
        if (missing.length) {
          // Lines saved on another device: fetch their names/prices for display.
          const products = await api.get("/shop/products").catch(() => []);
          for (const line of missing) {
            const product = products.find((p) => p.id === line.product_id);
            const variant = product?.variants?.find((v) => v.id === line.variant_id) || null;
            if (product) {
              local.push({
                product_id: product.id,
                variant_id: variant?.id || null,
                variant_label: variant?.label || null,
                name: product.name,
                price: variant ? variant.price : product.price,
                image_url: (product.image_urls || "").split(",").filter(Boolean)[0] || null,
                quantity: line.quantity,
              });
            }
          }
        }
        replaceCart(local);
        await api.put("/shop/cart", { items: toServer(local) });
      } catch {
        /* the browser cart still works on its own */
      } finally {
        merging.current = false;
      }
    }

    function pushSoon() {
      if (!isShopper() || merging.current) return;
      clearTimeout(timer.current);
      timer.current = setTimeout(() => api.put("/shop/cart", { items: toServer(getCart()) }).catch(() => {}), 1500);
    }

    mergeFromServer();
    window.addEventListener(AUTH_CHANGED_EVENT, mergeFromServer);
    window.addEventListener(CART_CHANGED_EVENT, pushSoon);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, mergeFromServer);
      window.removeEventListener(CART_CHANGED_EVENT, pushSoon);
      clearTimeout(timer.current);
    };
  }, []);

  return null;
}
