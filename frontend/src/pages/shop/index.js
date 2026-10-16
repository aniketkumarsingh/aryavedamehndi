import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import { addToCart } from "@/lib/cart";

export default function Shop() {
  const [products, setProducts] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [justAdded, setJustAdded] = useState(null);

  useEffect(() => {
    api
      .get("/shop/products")
      .then(setProducts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  function handleAdd(product) {
    addToCart(product, 1);
    setJustAdded(product.id);
    setTimeout(() => setJustAdded(null), 1500);
  }

  return (
    <div className="flex flex-col gap-6">
      <Head>
        <title>Shop — AryaVeda Mehndi</title>
      </Head>
      <div>
        <h1 className="text-2xl">Our Mehndi Products</h1>
        <p className="text-sm text-ink-soft">100% natural, organic henna cones — delivered to your door.</p>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-ink-soft">Loading products…</p>}
      {!loading && products.length === 0 && !error && (
        <p className="text-sm text-ink-soft">No products available right now — check back soon.</p>
      )}

      <div className="grid sm:grid-cols-3 gap-4">
        {products.map((p) => {
          const images = (p.image_urls || "").split(",").filter(Boolean);
          return (
            <div key={p.id} className="card overflow-hidden flex flex-col">
              <img
                src={images[0] || "/logo/mark.svg"}
                alt={p.name}
                className="w-full h-40 object-contain bg-ivory border-b border-line p-4"
              />
              <div className="p-4 flex flex-col gap-1 flex-1">
                <h3 className="font-semibold">{p.name}</h3>
                {p.description && <p className="text-sm text-ink-soft line-clamp-2">{p.description}</p>}
                <p className="text-lg font-semibold text-maroon-soft mt-1">₹{p.price}</p>
                <p className="text-xs text-ink-soft">
                  {p.stock_quantity > 0 ? `${p.stock_quantity} in stock` : "Out of stock"}
                </p>
                <button
                  className="btn-primary text-sm mt-2"
                  disabled={p.stock_quantity <= 0}
                  onClick={() => handleAdd(p)}
                >
                  {justAdded === p.id ? "Added ✓" : p.stock_quantity > 0 ? "Add to Cart" : "Out of Stock"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <Link href="/cart" className="btn-secondary self-start text-sm">
        View Cart
      </Link>
    </div>
  );
}
