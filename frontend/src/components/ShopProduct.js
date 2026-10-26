import { useState } from "react";
import { addToCart } from "@/lib/cart";
import { track } from "@/lib/analytics";

export const SHOP_CATEGORIES = [
  { key: "all", label: "All" },
  { key: "body-art", label: "Mehndi & Body Art" },
  { key: "hair", label: "Hair Care" },
  { key: "skin", label: "Skin & Body" },
  { key: "traditional", label: "Traditional" },
  { key: "tools", label: "Tools" },
  { key: "learn", label: "Learn & Practice" },
  { key: "decor", label: "Ceremony & Decor" },
  { key: "gifts", label: "Kits & Gifts" },
];

const DETAILS = [
  ["ingredients", "Ingredients"],
  ["how_to_use", "How to use"],
  ["safety_notes", "Safety"],
  ["shelf_life", "Shelf life"],
  ["storage", "Storage"],
];

// Licensed products list ingredients; tools, decor and gifts list what they're made of.
const detailLabel = (product, key, label) => (key === "ingredients" && !product.requires_licence ? "Materials" : label);

export const hasDetails = (product) => DETAILS.some(([k]) => product[k]);
export const productImages = (product) => (product.image_urls || "").split(",").filter(Boolean);

/** The selected pack size, starting on the first one in stock. */
export function useVariant(product) {
  const variants = product.variants || [];
  const [variantId, setVariantId] = useState(() => (variants.find((v) => v.stock_quantity > 0) || variants[0])?.id);
  const variant = variants.find((v) => v.id === variantId) || null;
  return {
    variants,
    variant,
    setVariantId,
    price: variant ? variant.price : product.price,
    stock: variant ? variant.stock_quantity : product.stock_quantity,
  };
}

export function addProductToCart(product, variant) {
  addToCart(product, 1, variant);
  const price = variant ? variant.price : product.price;
  track("add_to_cart", {
    currency: "INR",
    value: price,
    items: [{ item_id: variant?.id || product.id, item_name: product.name, item_variant: variant?.label, price, quantity: 1 }],
  });
}

export function IllustrativeBadge({ product }) {
  if (product.image_kind !== "illustrative") return null;
  return (
    <span className="absolute left-2 bottom-2 rounded-full bg-ivory-raised/90 border border-line px-2 py-0.5 text-[0.68rem] font-semibold text-ink-soft">
      Illustrative image
    </span>
  );
}

export function VariantPicker({ variants, variant, onPick }) {
  if (variants.length === 1) return <p className="text-xs text-ink-soft">{variants[0].label}</p>;
  if (variants.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Pack size">
      {variants.map((v) => (
        <button
          key={v.id}
          type="button"
          role="radio"
          aria-checked={v.id === variant?.id}
          onClick={() => onPick(v.id)}
          className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
            v.id === variant?.id ? "bg-maroon border-maroon text-ivory-raised" : "border-line bg-ivory-raised text-ink-soft hover:border-gold"
          }`}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

export function ProductDetails({ product, className = "" }) {
  return (
    <dl className={`text-xs flex flex-col gap-2 ${className}`}>
      {DETAILS.filter(([k]) => product[k]).map(([k, label]) => (
        <div key={k}>
          <dt className="font-semibold text-ink">{detailLabel(product, k, label)}</dt>
          <dd className="text-ink-soft">{product[k]}</dd>
        </div>
      ))}
    </dl>
  );
}
