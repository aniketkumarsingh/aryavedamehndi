import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import SocialMeta from "@/components/SocialMeta";
import {
  IllustrativeBadge,
  ProductDetails,
  SHOP_CATEGORIES,
  VariantPicker,
  addProductToCart,
  hasDetails,
  productImages,
  useVariant,
} from "@/components/ShopProduct";

function MaybeLink({ href, className, children }) {
  return href ? <Link href={href} className={className}>{children}</Link> : <div className={className}>{children}</div>;
}

function ProductCard({ product, onAdd, added }) {
  const images = productImages(product);
  const { variants, variant, setVariantId, price, stock } = useVariant(product);
  const [open, setOpen] = useState(false);
  const href = product.slug ? `/shop/${product.slug}` : null;

  return (
    <div className="card overflow-hidden flex flex-col">
      <MaybeLink href={href} className="relative block">
        <img src={images[0] || "/logo/mark.svg"} alt={product.name} className="w-full aspect-square object-cover bg-ivory border-b border-line" />
        <IllustrativeBadge product={product} />
      </MaybeLink>
      <div className="p-4 flex flex-col gap-2 flex-1">
        <MaybeLink href={href} className="font-semibold leading-snug hover:underline">{product.name}</MaybeLink>
        {product.description && <p className="text-sm text-ink-soft line-clamp-3">{product.description}</p>}
        <VariantPicker variants={variants} variant={variant} onPick={setVariantId} />

        <div className="mt-auto flex flex-col gap-1">
          <p className="text-lg font-semibold text-maroon-soft">
            ₹{price} <span className="text-xs font-normal text-ink-soft">MRP, incl. taxes</span>
          </p>
          <p className="text-xs text-ink-soft">{stock > 0 ? `${stock} in stock` : "Out of stock"}</p>
          <button className="btn-primary text-sm mt-1" disabled={stock <= 0} onClick={() => onAdd(product, variant)}>
            {added ? "Added ✓" : stock > 0 ? "Add to Cart" : "Out of Stock"}
          </button>
          {hasDetails(product) && (
            <button type="button" className="text-xs font-semibold text-gold self-start mt-1" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "Hide details" : product.requires_licence ? "Ingredients, use & safety" : "Details & care"}
            </button>
          )}
        </div>

        {open && <ProductDetails product={product} className="border-t border-line pt-3" />}
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
    addProductToCart(product, variant);
    setJustAdded(product.id);
    setTimeout(() => setJustAdded(null), 1500);
  }

  const available = SHOP_CATEGORIES.filter((c) => c.key === "all" || products.some((p) => p.category === c.key));
  const shown = category === "all" ? products : products.filter((p) => p.category === category);
  const anyIllustrative = shown.some((p) => p.image_kind === "illustrative");

  return (
    <div className="flex flex-col gap-6">
      <Head>
        <title>Shop — AryaVeda Mehndi</title>
        <meta key="description" name="description" content="Natural mehndi products, tools, practice kits, ceremony decor and gifts from AryaVeda Mehndi." />
      </Head>
      <SocialMeta
        title="Shop — AryaVeda Mehndi"
        description="Natural mehndi products, tools, practice kits, ceremony decor and gifts."
        path="/shop"
      />
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
