import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { ORDER_STATUS_LABELS, PAYMENT_STATUS_LABELS, REFUND_STATUS_LABELS, SHIPMENT_STATUS_LABELS, canCancel, hasDocument } from "@/lib/orderStatus";
import { payShopOrder } from "@/lib/shopPayment";
import { useLanguage } from "@/lib/useLanguage";

const formatDate = (d) => (d ? new Date(d).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : null);

function Timeline({ order }) {
  const steps = [
    { key: "confirmed", label: "Confirmed", at: order.confirmed_at },
    { key: "shipped", label: "Shipped", at: order.shipped_at },
    { key: "delivered", label: "Delivered", at: order.delivered_at },
  ];
  return (
    <ol className="grid grid-cols-3 gap-2 mt-4" aria-label="Order progress">
      {steps.map((s) => (
        <li key={s.key} className="flex flex-col gap-1">
          <span className={`h-1.5 rounded-full ${s.at ? "bg-maroon" : "bg-line"}`} />
          <span className={`text-xs font-semibold ${s.at ? "text-ink" : "text-ink-soft"}`}>{s.label}</span>
          {s.at && <span className="text-[0.68rem] text-ink-soft">{formatDate(s.at)}</span>}
        </li>
      ))}
    </ol>
  );
}

function DeliveryIssue({ order, shipment, onDone }) {
  const [mode, setMode] = useState(null); // "change_address"
  const [form, setForm] = useState({ address: order.shipping_address, pincode: order.shipping_pincode || "", phone: order.shipping_phone });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function answer(action, details = {}) {
    if (action === "cancel" && !window.confirm("Cancel this delivery? The parcel goes back to us" + (order.payment_method === "online" ? " and you're refunded once it arrives." : "."))) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/shop/orders/${order.id}/delivery-issue`, { action, ...details });
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm flex flex-col gap-2" role="alert">
      <p>
        <b>The courier couldn&apos;t deliver your order</b>
        {shipment.events.length > 0 && shipment.events[shipment.events.length - 1].description ? ` (${shipment.events[shipment.events.length - 1].description})` : ""}. What would you like to do?
        <span className="block text-xs text-ink-soft">If we don&apos;t hear from you within 24 hours, we&apos;ll ask them to try again.</span>
      </p>
      {mode === "change_address" ? (
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); answer("change_address", form); }}>
          <textarea className="input text-sm" required value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} aria-label="New address" />
          <div className="grid grid-cols-2 gap-2">
            <input className="input text-sm" inputMode="numeric" maxLength={6} placeholder="PIN code" required value={form.pincode}
              onChange={(e) => setForm({ ...form, pincode: e.target.value.replace(/\D/g, "") })} />
            <input className="input text-sm" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary text-xs" disabled={busy}>Deliver here</button>
            <button type="button" className="text-xs underline" onClick={() => setMode(null)}>Back</button>
          </div>
        </form>
      ) : (
        <div className="flex gap-2 flex-wrap">
          <button className="btn-primary text-xs" disabled={busy} onClick={() => answer("reattempt")}>Try again</button>
          <button className="btn-secondary text-xs" disabled={busy} onClick={() => setMode("change_address")}>Change address</button>
          <button className="text-xs text-red-700 underline" disabled={busy} onClick={() => answer("cancel")}>Cancel delivery</button>
        </div>
      )}
      {error && <p className="text-xs text-red-700">{error}</p>}
    </div>
  );
}

function ShipmentTracking({ shipment, trackLabel }) {
  const events = [...shipment.events].reverse(); // newest first
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="text-sm">
        <b>{SHIPMENT_STATUS_LABELS[shipment.status] || shipment.status}</b>
        {shipment.courier_name && ` · ${shipment.courier_name}`}
        {shipment.awb && ` · AWB ${shipment.awb}`}
        {shipment.tracking_url && (
          <>
            {" "}·{" "}
            <a href={shipment.tracking_url} target="_blank" rel="noopener noreferrer" className="underline text-gold font-semibold">{trackLabel}</a>
          </>
        )}
      </p>
      <ol className="mt-2 flex flex-col gap-2 border-l-2 border-line pl-3" aria-label="Tracking history">
        {events.map((e, i) => (
          <li key={`${e.occurred_at}-${i}`} className="text-xs relative">
            <span className={`absolute -left-[19px] top-1 h-2.5 w-2.5 rounded-full ${i === 0 ? "bg-maroon" : "bg-line"}`} />
            <span className={i === 0 ? "font-semibold text-ink" : "text-ink-soft"}>{SHIPMENT_STATUS_LABELS[e.status] || e.status}</span>
            {e.description && <span className="text-ink-soft"> — {e.description}</span>}
            {e.location && <span className="text-ink-soft"> · {e.location}</span>}
            <span className="block text-[0.68rem] text-ink-soft">{formatDate(e.occurred_at)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function OrderDetail() {
  const router = useRouter();
  const { id } = router.query;
  const { t } = useLanguage();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get(`/shop/orders/${id}`).then(setOrder), [id]);

  useEffect(() => {
    if (id) load().catch((e) => setError(e.message));
  }, [id, load]);

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
    // Whatever happened, show where the order now stands.
    await load().catch(() => {});
    setBusy(false);
  }

  function cancel() {
    const paid = order.payment_status === "paid";
    if (!window.confirm(paid ? "Cancel this order? Your payment will be refunded in full." : "Cancel this order?")) return;
    act(() => api.post(`/shop/orders/${id}/cancel`, {}));
  }

  if (error && !order) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">Loading order…</p>;

  const isCod = order.payment_method === "cod";
  const docLabel = order.invoice_number ? `Invoice ${order.invoice_number}` : "Receipt";
  const paymentLine =
    order.payment_status === "paid" || order.payment_status === "partially_refunded"
      ? `Paid ₹${order.amount_paid} online`
      : PAYMENT_STATUS_LABELS[order.payment_status] || order.payment_status;

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>Order Details — AryaVeda Mehndi</title>
      </Head>
      {order.status === "pending" && <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />}

      <div className="card p-5">
        <div className="flex justify-between items-start gap-3">
          <div>
            <h1 className="text-xl">Order #{order.id.slice(0, 8).toUpperCase()}</h1>
            <p className="text-xs text-ink-soft mt-1">Placed {formatDate(order.created_at)}</p>
          </div>
          <span className="chip whitespace-nowrap">{ORDER_STATUS_LABELS[order.status] || order.status}</span>
        </div>
        <p className="text-sm mt-3">
          {isCod ? "Cash on Delivery" : "Online payment"} · <b>{paymentLine}</b>
          {order.amount_refunded > 0 && ` · ₹${order.amount_refunded} refunded`}
        </p>
        {isCod && order.payment_status === "cod_due" && order.status !== "cancelled" && (
          <p className="text-sm text-ink-soft mt-1">Please keep ₹{order.total_amount} ready for the courier.</p>
        )}

        {order.status === "cancelled" || order.status === "returned" ? (
          <p className="text-sm mt-3">{order.cancel_reason || (order.status === "returned" ? "This parcel came back to us." : "This order was cancelled.")}</p>
        ) : (
          order.status !== "pending" && <Timeline order={order} />
        )}

        {order.shipments?.length > 0
          ? order.shipments.map((s) => (
              <div key={s.id}>
                {s.ndr_status === "open" && <DeliveryIssue order={order} shipment={s} onDone={() => load().catch(() => {})} />}
                {s.ndr_status === "answered" && s.status === "ndr" && (
                  <p className="text-xs text-ink-soft mt-3">Thanks — we&apos;ve passed your choice to the courier.</p>
                )}
                <ShipmentTracking shipment={s} trackLabel={t("order_track")} />
              </div>
            ))
          : order.tracking_number && (
              <p className="text-sm mt-3">
                {order.courier_name || "Courier"} · Tracking no. <b>{order.tracking_number}</b>
                {order.tracking_url && (
                  <>
                    {" "}·{" "}
                    <a href={order.tracking_url} target="_blank" rel="noopener noreferrer" className="underline text-gold font-semibold">{t("order_track")}</a>
                  </>
                )}
              </p>
            )}

        {error && <p className="text-sm text-red-700 mt-3">{error}</p>}
        {order.status === "pending" && (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-sm">{t("order_unpaid_note")}</p>
            <button className="btn-primary self-start" onClick={() => act(() => payShopOrder(order))} disabled={busy}>
              {busy ? t("order_please_wait") : t("order_pay_now", { amount: order.total_amount })}
            </button>
          </div>
        )}
        {canCancel(order) && (
          <button className="text-xs text-red-700 mt-3 block" onClick={cancel} disabled={busy}>
            {t("order_cancel")}
          </button>
        )}
      </div>

      {order.refunds.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">Refunds</h2>
          <div className="flex flex-col gap-2 text-sm">
            {order.refunds.map((r) => (
              <div key={r.id} className="flex justify-between items-start gap-3 border-b border-line pb-2 last:border-b-0">
                <div>
                  <p>
                    ₹{r.amount_refunded ?? r.amount_requested ?? order.amount_paid} · <b>{REFUND_STATUS_LABELS[r.status] || r.status}</b>
                  </p>
                  {r.reason && <p className="text-xs text-ink-soft">{r.reason}</p>}
                  {r.status !== "processed" && r.status !== "failed" && (
                    <p className="text-xs text-ink-soft">Banks usually show refunds within 5–7 working days of processing.</p>
                  )}
                </div>
                {r.credit_note_number && (
                  <button className="text-xs underline text-maroon-soft whitespace-nowrap" disabled={busy}
                    onClick={() => act(() => downloadFile(`/shop/refunds/${r.id}/credit-note.pdf`, `${r.credit_note_number}.pdf`))}>
                    Credit note
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5">
        <div className="flex justify-between items-center mb-2">
          <h2 className="font-semibold">Items</h2>
          {hasDocument(order) && order.status !== "pending" && (
            <div className="flex gap-3 text-xs">
              <Link href={`/shop/orders/${order.id}/invoice`} className="underline text-maroon-soft">{t("order_receipt")}</Link>
              <button className="underline text-maroon-soft" disabled={busy}
                onClick={() => act(() => downloadFile(`/shop/orders/${order.id}/document.pdf`, `${order.invoice_number || `receipt-${order.id.slice(0, 8)}`}.pdf`))}>
                {docLabel} (PDF)
              </button>
            </div>
          )}
        </div>
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
        <div className="flex flex-col gap-1 text-sm mt-3 pt-2 border-t border-line">
          {order.items_amount != null && <div className="flex justify-between"><span>Items</span><span>₹{order.items_amount}</span></div>}
          {order.discount_amount > 0 && (
            <div className="flex justify-between text-green-800"><span>Coupon {order.coupon_code}</span><span>−₹{order.discount_amount}</span></div>
          )}
          <div className="flex justify-between"><span>Delivery</span><span>{order.shipping_fee > 0 ? `₹${order.shipping_fee}` : "Free"}</span></div>
          {order.cod_fee > 0 && <div className="flex justify-between"><span>Cash on Delivery charge</span><span>₹{order.cod_fee}</span></div>}
        </div>
        <div className="flex justify-between font-semibold mt-3 pt-2 border-t border-line">
          <span>Total</span>
          <span className="text-maroon-soft">₹{order.total_amount}</span>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Delivery Address</h2>
        <p className="text-sm">{order.shipping_name}</p>
        <p className="text-sm text-ink-soft">{order.shipping_phone}{order.contact_email ? ` · ${order.contact_email}` : ""}</p>
        <p className="text-sm text-ink-soft whitespace-pre-line">{order.shipping_address}</p>
        {(order.shipping_state || order.shipping_pincode) && (
          <p className="text-sm text-ink-soft">{[order.shipping_state, order.shipping_pincode].filter(Boolean).join(" - ")}</p>
        )}
      </div>
    </div>
  );
}
