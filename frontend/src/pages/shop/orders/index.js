import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";

const STATUS_LABELS = {
  pending: "Awaiting Payment",
  paid: "Paid — Preparing to Ship",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export default function MyOrders() {
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/shop/orders")
      .then(setOrders)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>My Orders — AryaVeda Mehndi</title>
      </Head>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl">My Orders</h1>
        <Link href="/shop" className="btn-secondary text-sm">
          Shop More
        </Link>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-ink-soft">Loading…</p>}
      {!loading && orders.length === 0 && !error && <p className="text-sm text-ink-soft">You haven&apos;t ordered anything yet.</p>}

      <div className="flex flex-col gap-3">
        {orders.map((o) => (
          <Link key={o.id} href={`/shop/orders/${o.id}`} className="card p-4 flex items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-sm">
                {o.items.map((i) => `${i.product_name} ×${i.quantity}`).join(", ")}
              </p>
              <p className="text-xs text-ink-soft">{new Date(o.created_at).toLocaleDateString()} · ₹{o.total_amount}</p>
            </div>
            <span className="chip whitespace-nowrap">{STATUS_LABELS[o.status] || o.status}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
