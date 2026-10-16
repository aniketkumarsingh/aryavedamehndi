import { useEffect, useState } from "react";
import { CART_CHANGED_EVENT, getCart } from "./cart";

export function useCart() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    setItems(getCart());
    function refresh() {
      setItems(getCart());
    }
    window.addEventListener(CART_CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(CART_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  return items;
}
