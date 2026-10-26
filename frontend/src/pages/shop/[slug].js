import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import SocialMeta, { SITE_URL, absoluteUrl } from "@/components/SocialMeta";
import { IllustrativeBadge, ProductDetails, SHOP_CATEGORIES, VariantPicker, addProductToCart, productImages, useVariant } from "@/components/ShopProduct";
import { track } from "@/lib/analytics";
import { api } from "@/lib/api";
import { fetchBackend } from "@/lib/serverApi";

/** Product details are server-rendered (ISR) so search engines, ad
 * platforms and link previews see them; this is the landing page the ad
 * product feed (/shop/feed.csv) links to. */
export async function getStaticPaths() {
  return { paths: [], fallback: "blocking" };
}

export async function getStaticProps({ params }) {
  let product;
  try {
    product = await fetchBackend(`/shop/products/by-slug/${encodeURIComponent(params.slug)}`);
  } catch {
    return { props: { product: null }, revalidate: 30 };
  }
  if (!product) return { notFound: true, revalidate: 60 };
  return { props: { product }, revalidate: 120 };
}

function productJsonLd(product, images) {
  const variants = product.variants?.length ? product.variants : [{ price: product.price, stock_quantity: product.stock_quantity }];
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.description,
    image: images.map(absoluteUrl),
    brand: { "@type": "Brand", name: "AryaVeda Mehndi" },
    offers: variants.map((v) => ({
      "@type": "Offer",
      priceCurrency: "INR",
      price: v.price,
      availability: v.stock_quantity > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
      url: `${SITE_URL}/shop/${product.slug}`,
    })),
  };
}

export default function ProductPage({ product: built }) {
  // The page is pre-built and refreshed every couple of minutes; fetch the
  // live record on open so stock and prices are never stale.
  const [product, setProduct] = useState(built);
  useEffect(() => {
    setProduct(built);
    if (!built?.slug) return;
    api.get(`/shop/products/by-slug/${encodeURIComponent(built.slug)}`).then(setProduct).catch(() => {});
  }, [built]);

  if (!product) return <p className="text-ink-soft">This product couldn&apos;t be loaded right now. Please try again shortly.</p>;
  return <Product product={product} />;
}

function Product({ product }) {
  const images = productImages(product);
  const { variants, variant, setVariantId, price, stock } = useVariant(product);
  const [added, setAdded] = useState(false);
  const category = SHOP_CATEGORIES.find((c) => c.key === product.category);

  useEffect(() => {
    track("view_item", { currency: "INR", value: product.price, items: [{ item_id: product.id, item_name: product.name, price: product.price }] });
  }, [product.id, product.name, product.price]);

  function add() {
    addProductToCart(product, variant);
    setAdded(true);
    setTimeout(() => setAdded(false), 1500);
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      <Head>
        <title>{`${product.name} | AryaVeda Mehndi Shop`}</title>
        <meta key="description" name="description" content={product.description || product.name} />
      </Head>
      <SocialMeta
        title={product.name}
        description={product.description}
        image={images[0]}
        path={`/shop/${product.slug}`}
        type="product"
        jsonLd={productJsonLd(product, images)}
      />

      <Link href="/shop" className="text-sm text-maroon-soft underline self-start">
        ← {category && category.key !== "all" ? category.label : "All products"}
      </Link>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="relative card overflow-hidden self-start">
          <img src={images[0] || "/logo/mark.svg"} alt={product.name} className="w-full aspect-square object-cover bg-ivory" />
          <IllustrativeBadge product={product} />
        </div>

        <div className="flex flex-col gap-3">
          <h1 className="text-2xl leading-tight">{product.name}</h1>
          {product.description && <p className="text-ink-soft">{product.description}</p>}
          <VariantPicker variants={variants} variant={variant} onPick={setVariantId} />
          <p className="text-2xl font-semibold text-maroon-soft">
            ₹{price} <span className="text-xs font-normal text-ink-soft">MRP, incl. taxes</span>
          </p>
          <p className="text-sm text-ink-soft">{stock > 0 ? `${stock} in stock` : "Out of stock"}</p>
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary" disabled={stock <= 0} onClick={add}>
              {added ? "Added ✓" : stock > 0 ? "Add to Cart" : "Out of Stock"}
            </button>
            <Link href="/cart" className="btn-secondary">
              View Cart
            </Link>
          </div>
          <ProductDetails product={product} className="card p-4 text-sm" />
          {product.image_kind === "illustrative" && (
            <p className="text-xs text-ink-soft">The image is AI-made to show the product type; the pack you receive may look different.</p>
          )}
          <p className="text-xs text-ink-soft">
            <Link href="/legal/shipping" className="underline">Delivery</Link> ·{" "}
            <Link href="/legal/refunds" className="underline">Returns &amp; refunds</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
