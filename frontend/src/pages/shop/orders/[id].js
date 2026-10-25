import { useEffect, useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";
import { api } from "@/lib/api";

const STATUS_LABELS = {
  pending: "Awaiting Payment",
  paid: "Paid — Preparing to Ship",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

const STATUS_STEPS = ["paid", "shipped", "delivered"];

export default function OrderDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api
      .get(`/shop/orders/${id}`)
      .then(setOrder)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">Loading order…</p>;

  const stepIndex = STATUS_STEPS.indexOf(order.status);

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>Order Details — AryaVeda Mehndi</title>
      </Head>
      <div className="card p-5">
        <div className="flex justify-between items-center">
          <h1 className="text-xl">Order</h1>
          <span className="chip">{STATUS_LABELS[order.status] || order.status}</span>
        </div>
        <p className="text-xs text-ink-soft mt-1">Placed {new Date(order.created_at).toLocaleString()}</p>

        {order.status !== "cancelled" && (
          <div className="flex items-center gap-2 mt-4">
            {STATUS_STEPS.map((step, i) => (
              <div key={step} className="flex items-center gap-2 flex-1">
                <div
                  className={`h-2.5 w-2.5 rounded-full flex-none ${i <= stepIndex ? "bg-maroon" : "bg-line"}`}
                  title={STATUS_LABELS[step]}
                />
                {i < STATUS_STEPS.length - 1 && (
                  <div className={`h-0.5 flex-1 ${i < stepIndex ? "bg-maroon" : "bg-line"}`} />
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Items</h2>
        <div className="flex flex-col gap-2">
          {order.items.map((item) => (
            <div key={item.product_id} className="flex justify-between text-sm border-b border-line pb-2 last:border-b-0">
              <span>
                {item.product_name}{item.variant_label ? ` (${item.variant_label})` : ""} × {item.quantity}
              </span>
              <span>₹{item.subtotal}</span>
            </div>
          ))}
        </div>
        <div className="flex justify-between font-semibold mt-3 pt-2 border-t border-line">
          <span>Total</span>
          <span className="text-maroon-soft">₹{order.total_amount}</span>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Delivery Address</h2>
        <p className="text-sm">{order.shipping_name}</p>
        <p className="text-sm text-ink-soft">{order.shipping_phone}</p>
        <p className="text-sm text-ink-soft">{order.shipping_address}</p>
      </div>
    </div>
  );
}
