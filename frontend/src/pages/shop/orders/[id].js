import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { RETURN_REASONS, canCancel, hasDocument, statusLabel } from "@/lib/orderStatus";
import { payShopOrder } from "@/lib/shopPayment";
import { useLanguage } from "@/lib/useLanguage";

const formatDate = (d) => (d ? new Date(d).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : null);

function Timeline({ order }) {
  const { t } = useLanguage();
  const steps = [
    { key: "confirmed", label: t("ot_confirmed"), at: order.confirmed_at },
    { key: "shipped", label: t("ot_shipped"), at: order.shipped_at },
    { key: "delivered", label: t("ot_delivered"), at: order.delivered_at },
  ];
  return (
    <ol className="grid grid-cols-3 gap-2 mt-4" aria-label={t("ot_progress")}>
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
  const { t } = useLanguage();
  const [mode, setMode] = useState(null); // "change_address"
  const [form, setForm] = useState({ address: order.shipping_address, pincode: order.shipping_pincode || "", phone: order.shipping_phone });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function answer(action, details = {}) {
    if (action === "cancel" && !window.confirm(order.payment_method === "online" ? t("ndr_cancel_confirm_online") : t("ndr_cancel_confirm"))) return;
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
        <b>{t("ndr_title")}</b>
        {shipment.events.length > 0 && shipment.events[shipment.events.length - 1].description ? ` (${shipment.events[shipment.events.length - 1].description})` : ""}. {t("ndr_question")}
        <span className="block text-xs text-ink-soft">{t("ndr_auto")}</span>
      </p>
      {mode === "change_address" ? (
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); answer("change_address", form); }}>
          <textarea className="input text-sm" required value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} aria-label={t("ndr_new_address")} />
          <div className="grid grid-cols-2 gap-2">
            <input className="input text-sm" inputMode="numeric" maxLength={6} placeholder={t("pin_code")} required value={form.pincode}
              onChange={(e) => setForm({ ...form, pincode: e.target.value.replace(/\D/g, "") })} />
            <input className="input text-sm" placeholder={t("cart_phone")} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary text-xs" disabled={busy}>{t("ndr_deliver_here")}</button>
            <button type="button" className="text-xs underline" onClick={() => setMode(null)}>{t("back")}</button>
          </div>
        </form>
      ) : (
        <div className="flex gap-2 flex-wrap">
          <button className="btn-primary text-xs" disabled={busy} onClick={() => answer("reattempt")}>{t("ndr_try_again")}</button>
          <button className="btn-secondary text-xs" disabled={busy} onClick={() => setMode("change_address")}>{t("ndr_change_address")}</button>
          <button className="text-xs text-red-700 underline" disabled={busy} onClick={() => answer("cancel")}>{t("ndr_cancel_delivery")}</button>
        </div>
      )}
      {error && <p className="text-xs text-red-700">{error}</p>}
    </div>
  );
}

function ReturnForm({ order, onDone, onCancel }) {
  const { t, lang } = useLanguage();
  const returnedQty = {};
  for (const r of order.returns.filter((r) => r.status !== "rejected")) for (const l of r.items) returnedQty[l.order_item_id] = (returnedQty[l.order_item_id] || 0) + l.quantity;
  const [qty, setQty] = useState({});
  const [reason, setReason] = useState("damaged");
  const [details, setDetails] = useState("");
  const [upi, setUpi] = useState("");
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    const items = Object.entries(qty).filter(([, n]) => n > 0).map(([order_item_id, quantity]) => ({ order_item_id, quantity }));
    if (!items.length) return setError(t("ret_choose_item"));
    const form = new FormData();
    form.append("items", JSON.stringify(items));
    form.append("reason_code", reason);
    if (details.trim()) form.append("details", details.trim());
    if (upi.trim()) form.append("refund_upi", upi.trim());
    for (const p of photos) form.append("photos", p);
    setBusy(true);
    setError("");
    try {
      await api.uploadForm(`/shop/orders/${order.id}/returns`, form);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card p-5 flex flex-col gap-3 text-sm">
      <h2 className="font-semibold">{t("ret_heading")}</h2>
      <p className="text-xs text-ink-soft">
        {t("ret_policy")}{" "}
        <Link href="/legal/refunds" className="underline">{t("policy_refund")}</Link>
      </p>
      {order.items.map((item) => {
        const left = item.quantity - (returnedQty[item.id] || 0);
        return (
          <label key={item.id} className="flex items-center justify-between gap-2">
            <span>{item.product_name}{item.variant_label ? ` (${item.variant_label})` : ""}</span>
            <select className="input w-auto text-xs" disabled={left <= 0} value={qty[item.id] || 0} onChange={(e) => setQty({ ...qty, [item.id]: Number(e.target.value) })}>
              {Array.from({ length: Math.max(left, 0) + 1 }, (_, n) => <option key={n} value={n}>{n === 0 ? t("ret_keep") : t("ret_return_n", { n })}</option>)}
            </select>
          </label>
        );
      })}
      <select className="input" value={reason} onChange={(e) => setReason(e.target.value)} aria-label={t("ret_reason")}>
        {RETURN_REASONS.map(([v]) => <option key={v} value={v}>{statusLabel("reason", v, lang)}</option>)}
      </select>
      <textarea className="input" placeholder={t("ret_details")} value={details} onChange={(e) => setDetails(e.target.value)} />
      <label className="text-xs flex flex-col gap-1">
        {["damaged", "wrong_item"].includes(reason) ? t("ret_photos_required") : t("ret_photos_optional")}
        <input type="file" accept="image/*" multiple onChange={(e) => setPhotos([...e.target.files].slice(0, 3))} />
      </label>
      {order.payment_method === "cod" && (
        <input className="input" required placeholder={t("ret_upi")} value={upi} onChange={(e) => setUpi(e.target.value)} />
      )}
      {error && <p className="text-xs text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button className="btn-primary text-sm" disabled={busy}>{busy ? t("ret_sending") : t("ret_submit")}</button>
        <button type="button" className="text-xs underline" onClick={onCancel}>{t("cancel")}</button>
      </div>
    </form>
  );
}

function ShipmentTracking({ shipment, trackLabel }) {
  const { t, lang } = useLanguage();
  const events = [...shipment.events].reverse(); // newest first
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="text-sm">
        {shipment.direction === "reverse" && <span className="chip mr-1">{t("track_return_pickup")}</span>}
        <b>{statusLabel("shipment", shipment.status, lang)}</b>
        {shipment.courier_name && ` · ${shipment.courier_name}`}
        {shipment.awb && ` · AWB ${shipment.awb}`}
        {shipment.tracking_url && (
          <>
            {" "}·{" "}
            <a href={shipment.tracking_url} target="_blank" rel="noopener noreferrer" className="underline text-gold font-semibold">{trackLabel}</a>
          </>
        )}
      </p>
      <ol className="mt-2 flex flex-col gap-2 border-l-2 border-line pl-3" aria-label={t("track_history")}>
        {events.map((e, i) => (
          <li key={`${e.occurred_at}-${i}`} className="text-xs relative">
            <span className={`absolute -left-[19px] top-1 h-2.5 w-2.5 rounded-full ${i === 0 ? "bg-maroon" : "bg-line"}`} />
            <span className={i === 0 ? "font-semibold text-ink" : "text-ink-soft"}>{statusLabel("shipment", e.status, lang)}</span>
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
  const { t, lang } = useLanguage();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState(false);

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
    if (!window.confirm(paid ? t("order_cancel_confirm_paid") : t("order_cancel_confirm"))) return;
    act(() => api.post(`/shop/orders/${id}/cancel`, {}));
  }

  if (error && !order) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">{t("order_loading")}</p>;

  const isCod = order.payment_method === "cod";
  const docLabel = order.invoice_number ? t("order_invoice", { number: order.invoice_number }) : t("order_receipt_only");
  const paymentLine =
    order.payment_status === "paid" || order.payment_status === "partially_refunded"
      ? t("order_paid_online", { amount: order.amount_paid })
      : statusLabel("payment", order.payment_status, lang);
  const couponOff = Math.round((order.discount_amount - (order.referral_discount || 0) - (order.wallet_amount || 0)) * 100) / 100;

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>{`${t("order_details")} — AryaVeda Mehndi`}</title>
      </Head>
      {order.status === "pending" && <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />}

      <div className="card p-5">
        <div className="flex justify-between items-start gap-3">
          <div>
            <h1 className="text-xl">{t("order_heading", { ref: order.id.slice(0, 8).toUpperCase() })}</h1>
            <p className="text-xs text-ink-soft mt-1">{t("order_placed", { date: formatDate(order.created_at) })}</p>
          </div>
          <span className="chip whitespace-nowrap">{statusLabel("order", order.status, lang)}</span>
        </div>
        <p className="text-sm mt-3">
          {isCod ? t("order_cod") : t("order_online")} · <b>{paymentLine}</b>
          {order.amount_refunded > 0 && ` · ${t("order_refunded_amount", { amount: order.amount_refunded })}`}
        </p>
        {isCod && order.payment_status === "cod_due" && order.status !== "cancelled" && (
          <p className="text-sm text-ink-soft mt-1">{t("order_cod_keep_ready", { amount: order.total_amount })}</p>
        )}

        {order.status === "cancelled" || order.status === "returned" ? (
          <p className="text-sm mt-3">{order.cancel_reason || (order.status === "returned" ? t("order_came_back") : t("order_was_cancelled"))}</p>
        ) : (
          order.status !== "pending" && <Timeline order={order} />
        )}

        {order.shipments?.length > 0
          ? order.shipments.map((s) => (
              <div key={s.id}>
                {s.ndr_status === "open" && <DeliveryIssue order={order} shipment={s} onDone={() => load().catch(() => {})} />}
                {s.ndr_status === "answered" && s.status === "ndr" && (
                  <p className="text-xs text-ink-soft mt-3">{t("ndr_answered")}</p>
                )}
                <ShipmentTracking shipment={s} trackLabel={t("order_track")} />
              </div>
            ))
          : order.tracking_number && (
              <p className="text-sm mt-3">
                {order.courier_name || t("courier")} · {t("tracking_no")} <b>{order.tracking_number}</b>
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

      {order.returns.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">{t("order_returns")}</h2>
          {order.returns.map((r) => (
            <div key={r.id} className="text-sm border-b border-line pb-2 last:border-b-0">
              <p><b>{statusLabel("return", r.status, lang)}</b> · ₹{r.refund_amount}</p>
              {r.admin_note && <p className="text-xs text-ink-soft">{r.admin_note}</p>}
            </div>
          ))}
        </div>
      )}

      {order.status === "delivered" && order.return_window_ends && new Date(order.return_window_ends + "Z") > new Date() && (
        returning ? (
          <ReturnForm order={order} onCancel={() => setReturning(false)} onDone={() => { setReturning(false); load().catch(() => {}); }} />
        ) : (
          <button className="btn-secondary text-sm self-start" onClick={() => setReturning(true)}>
            {t("ret_button", { date: new Date(order.return_window_ends + "Z").toLocaleDateString("en-IN", { day: "numeric", month: "short" }) })}
          </button>
        )
      )}

      {order.refunds.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">{t("order_refunds")}</h2>
          <div className="flex flex-col gap-2 text-sm">
            {order.refunds.map((r) => (
              <div key={r.id} className="flex justify-between items-start gap-3 border-b border-line pb-2 last:border-b-0">
                <div>
                  <p>
                    ₹{r.amount_refunded ?? r.amount_requested ?? order.amount_paid} · <b>{statusLabel("refund", r.status, lang)}</b>
                  </p>
                  {r.reason && <p className="text-xs text-ink-soft">{r.reason}</p>}
                  {r.status !== "processed" && r.status !== "failed" && (
                    <p className="text-xs text-ink-soft">{t("refund_bank_note")}</p>
                  )}
                </div>
                {r.credit_note_number && (
                  <button className="text-xs underline text-maroon-soft whitespace-nowrap" disabled={busy}
                    onClick={() => act(() => downloadFile(`/shop/refunds/${r.id}/credit-note.pdf`, `${r.credit_note_number}.pdf`))}>
                    {t("credit_note")}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5">
        <div className="flex justify-between items-center mb-2">
          <h2 className="font-semibold">{t("order_items")}</h2>
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
          {order.items_amount != null && <div className="flex justify-between"><span>{t("cart_items")}</span><span>₹{order.items_amount}</span></div>}
          {couponOff > 0 && (
            <div className="flex justify-between text-green-800"><span>{t("order_coupon", { code: order.coupon_code || "" })}</span><span>−₹{couponOff}</span></div>
          )}
          {order.referral_discount > 0 && (
            <div className="flex justify-between text-green-800"><span>{t("cart_referral_discount")}</span><span>−₹{order.referral_discount}</span></div>
          )}
          {order.wallet_amount > 0 && (
            <div className="flex justify-between text-green-800"><span>{t("order_wallet")}</span><span>−₹{order.wallet_amount}</span></div>
          )}
          <div className="flex justify-between"><span>{t("cart_delivery")}</span><span>{order.shipping_fee > 0 ? `₹${order.shipping_fee}` : t("cart_free")}</span></div>
          {order.cod_fee > 0 && <div className="flex justify-between"><span>{t("order_cod_charge")}</span><span>₹{order.cod_fee}</span></div>}
        </div>
        <div className="flex justify-between font-semibold mt-3 pt-2 border-t border-line">
          <span>{t("cart_total")}</span>
          <span className="text-maroon-soft">₹{order.total_amount}</span>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold mb-2">{t("order_address")}</h2>
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
