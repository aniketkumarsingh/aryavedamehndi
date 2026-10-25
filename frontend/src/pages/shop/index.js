import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import { addToCart } from "@/lib/cart";

const CATEGORIES = [
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

function ProductCard({ product, onAdd, added }) {
  const images = (product.image_urls || "").split(",").filter(Boolean);
  const variants = product.variants || [];
  const [variantId, setVariantId] = useState(() => (variants.find((v) => v.stock_quantity > 0) || variants[0])?.id);
  const [open, setOpen] = useState(false);
  const variant = variants.find((v) => v.id === variantId) || null;
  const price = variant ? variant.price : product.price;
  const stock = variant ? variant.stock_quantity : product.stock_quantity;
  const hasDetails = DETAILS.some(([k]) => product[k]);

  return (
    <div className="card overflow-hidden flex flex-col">
      <div className="relative">
        <img src={images[0] || "/logo/mark.svg"} alt={product.name} className="w-full aspect-square object-cover bg-ivory border-b border-line" />
        {product.image_kind === "illustrative" && (
          <span className="absolute left-2 bottom-2 rounded-full bg-ivory-raised/90 border border-line px-2 py-0.5 text-[0.68rem] font-semibold text-ink-soft">
            Illustrative image
          </span>
        )}
      </div>
      <div className="p-4 flex flex-col gap-2 flex-1">
        <h3 className="font-semibold leading-snug">{product.name}</h3>
        {product.description && <p className="text-sm text-ink-soft line-clamp-3">{product.description}</p>}

        {variants.length > 1 && (
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Pack size">
            {variants.map((v) => (
              <button
                key={v.id}
                type="button"
                role="radio"
                aria-checked={v.id === variantId}
                onClick={() => setVariantId(v.id)}
                className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                  v.id === variantId ? "bg-maroon border-maroon text-ivory-raised" : "border-line bg-ivory-raised text-ink-soft hover:border-gold"
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
        )}
        {variants.length === 1 && <p className="text-xs text-ink-soft">{variants[0].label}</p>}

        <div className="mt-auto flex flex-col gap-1">
          <p className="text-lg font-semibold text-maroon-soft">
            ₹{price} <span className="text-xs font-normal text-ink-soft">MRP, incl. taxes</span>
          </p>
          <p className="text-xs text-ink-soft">{stock > 0 ? `${stock} in stock` : "Out of stock"}</p>
          <button className="btn-primary text-sm mt-1" disabled={stock <= 0} onClick={() => onAdd(product, variant)}>
            {added ? "Added ✓" : stock > 0 ? "Add to Cart" : "Out of Stock"}
          </button>
          {hasDetails && (
            <button type="button" className="text-xs font-semibold text-gold self-start mt-1" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "Hide details" : product.requires_licence ? "Ingredients, use & safety" : "Details & care"}
            </button>
          )}
        </div>

        {open && (
          <dl className="text-xs flex flex-col gap-2 border-t border-line pt-3">
            {DETAILS.filter(([k]) => product[k]).map(([k, label]) => (
              <div key={k}>
                <dt className="font-semibold text-ink">{detailLabel(product, k, label)}</dt>
                <dd className="text-ink-soft">{product[k]}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}

export default function Shop() {
  const [products, setProducts] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [justAdded, setJustAdded] = useState(null);
  const [category, setCategory] = useState("all");

  useEffect(() => {
    api
      .get("/shop/products")
      .then(setProducts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  function handleAdd(product, variant) {
    addToCart(product, 1, variant);
    setJustAdded(product.id);
    setTimeout(() => setJustAdded(null), 1500);
  }

  const available = CATEGORIES.filter((c) => c.key === "all" || products.some((p) => p.category === c.key));
  const shown = category === "all" ? products : products.filter((p) => p.category === category);
  const anyIllustrative = shown.some((p) => p.image_kind === "illustrative");

  return (
    <div className="flex flex-col gap-6">
      <Head>
        <title>Shop — AryaVeda Mehndi</title>
      </Head>
      <div>
        <h1 className="text-2xl">Our Mehndi Products</h1>
        <p className="text-sm text-ink-soft">Natural henna for mehndi, hair and skin, made under the AryaVeda name and delivered to your door.</p>
      </div>

      {available.length > 2 && (
        <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Product category">
          {available.map((c) => (
            <button
              key={c.key}
              role="tab"
              aria-selected={category === c.key}
              onClick={() => setCategory(c.key)}
              className={category === c.key ? "btn-primary text-sm" : "btn-secondary text-sm"}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-ink-soft">Loading products…</p>}
      {!loading && products.length === 0 && !error && (
        <p className="text-sm text-ink-soft">No products available right now — check back soon.</p>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {shown.map((p) => (
          <ProductCard key={p.id} product={p} onAdd={handleAdd} added={justAdded === p.id} />
        ))}
      </div>

      {anyIllustrative && (
        <p className="text-xs text-ink-soft">Images marked “Illustrative image” are AI-made to show the product type; the pack you receive may look different.</p>
      )}

      <Link href="/cart" className="btn-secondary self-start text-sm">
        View Cart
      </Link>
    </div>
  );
}
