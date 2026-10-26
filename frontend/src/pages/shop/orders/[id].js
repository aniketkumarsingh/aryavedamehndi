import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { payShopOrder } from "@/lib/shopPayment";
import { useLanguage } from "@/lib/useLanguage";

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
  const { t } = useLanguage();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function cancel() {
    if (!window.confirm(order.status === "paid" ? "Cancel this order? Your payment will be refunded in full." : "Cancel this order?")) return;
    setBusy(true);
    setError("");
    try {
      setOrder(await api.post(`/shop/orders/${id}/cancel`, {}));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function payNow() {
    setBusy(true);
    setError("");
    try {
      await payShopOrder(order);
    } catch (e) {
      setError(e.message);
    }
    // Paid, closed or failed - reload to show where the order stands.
    try {
      setOrder(await api.get(`/shop/orders/${id}`));
    } catch {
      /* keep what we have */
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!id) return;
    api
      .get(`/shop/orders/${id}`)
      .then(setOrder)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error && !order) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">Loading order…</p>;

  const stepIndex = STATUS_STEPS.indexOf(order.status);

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>Order Details — AryaVeda Mehndi</title>
      </Head>
      {order.status === "pending" && <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />}
      <div className="card p-5">
        <div className="flex justify-between items-center">
          <h1 className="text-xl">Order</h1>
          <span className="chip">{STATUS_LABELS[order.status] || order.status}</span>
        </div>
        <p className="text-xs text-ink-soft mt-1">Placed {new Date(order.created_at).toLocaleString()}</p>
        {order.status === "cancelled" && (
          <p className="text-sm mt-3">
            {order.cancel_reason || "This order was cancelled."}
            {order.refund_status === "refunded" && ` ₹${order.total_amount} has been refunded to your original payment method (usually 5–7 working days).`}
            {order.refund_status === "failed" && " Your refund is being processed by our team."}
          </p>
        )}
        {["paid", "shipped", "delivered"].includes(order.status) && (
          <Link href={`/shop/orders/${order.id}/invoice`} className="text-sm underline text-maroon-soft mt-2 inline-block">
            {t("order_receipt")}
          </Link>
        )}
        {order.tracking_number && (
          <p className="text-sm mt-3">
            Shipped with <b>{order.courier_name || "our courier"}</b> · Tracking no. <b>{order.tracking_number}</b>
            {order.tracking_url && (
              <>
                {" "}
                · <a href={order.tracking_url} target="_blank" rel="noopener noreferrer" className="underline text-gold font-semibold">{t("order_track")}</a>
              </>
            )}
          </p>
        )}
        {error && <p className="text-sm text-red-700 mt-2">{error}</p>}
        {order.status === "pending" && (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-sm">{t("order_unpaid_note")}</p>
            <button className="btn-primary self-start" onClick={payNow} disabled={busy}>
              {busy ? t("order_please_wait") : t("order_pay_now", { amount: order.total_amount })}
            </button>
          </div>
        )}
        {(order.status === "pending" || order.status === "paid") && (
          <button className="text-xs text-red-700 mt-3 self-start" onClick={cancel} disabled={busy}>
            {t("order_cancel")}
          </button>
        )}

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
            <div key={`${item.product_id}:${item.variant_id || ""}`} className="flex justify-between text-sm border-b border-line pb-2 last:border-b-0">
              <span>
                {item.product_name}{item.variant_label ? ` (${item.variant_label})` : ""} × {item.quantity}
              </span>
              <span>₹{item.subtotal}</span>
            </div>
          ))}
        </div>
        {order.items_amount != null && (
          <div className="flex flex-col gap-1 text-sm mt-3 pt-2 border-t border-line">
            <div className="flex justify-between"><span>Items</span><span>₹{order.items_amount}</span></div>
            {order.discount_amount > 0 && (
              <div className="flex justify-between text-green-800"><span>Coupon {order.coupon_code}</span><span>−₹{order.discount_amount}</span></div>
            )}
            <div className="flex justify-between"><span>Delivery</span><span>{order.shipping_fee > 0 ? `₹${order.shipping_fee}` : "Free"}</span></div>
          </div>
        )}
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
