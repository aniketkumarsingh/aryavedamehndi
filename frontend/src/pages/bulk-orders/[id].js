import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { Icon, Receipt, StatusTracker } from "@/components/OrderParts";
import PricePromise from "@/components/PricePromise";
import { api } from "@/lib/api";
import { categoryLabel, formatPriceRange } from "@/lib/designs";
import { DEPOSIT_LABELS, bulkOccasionLabel, estimateSummary, formatInr } from "@/lib/pricing";

export default function BulkOrderDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    if (!id) return;
    api.get(`/bulk-orders/${id}`).then(setOrder).catch((e) => setError(e.message));
  }, [id]);
  useEffect(refresh, [refresh]);

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      setOrder(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function payDeposit() {
    setBusy(true);
    setError("");
    try {
      const rp = await api.post(`/bulk-orders/${id}/advance/order`, {});
      const verify = (r) =>
        api.post(`/bulk-orders/${id}/advance/verify`, {
          razorpay_order_id: r.razorpay_order_id,
          razorpay_payment_id: r.razorpay_payment_id,
          razorpay_signature: r.razorpay_signature,
        });
      if (rp.razorpay_key_id === "dev_mode_no_key") {
        setOrder(await verify({ razorpay_order_id: rp.razorpay_order_id, razorpay_payment_id: "dev_payment", razorpay_signature: "dev" }));
        return;
      }
      new window.Razorpay({
        key: rp.razorpay_key_id,
        amount: Math.round(rp.amount * 100),
        currency: rp.currency,
        name: "AryaVeda Mehndi",
        description: "Event deposit",
        order_id: rp.razorpay_order_id,
        handler: async (response) => setOrder(await verify(response)),
      }).open();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    const late = order.advance_status === "paid" && new Date(order.event_at + "Z") - Date.now() < 24 * 3600 * 1000;
    const msg = late
      ? `The event is less than 24 hours away — cancelling now forfeits your ${formatInr(order.advance_amount)} deposit. Cancel anyway?`
      : order.advance_status === "paid"
        ? `Cancel this order? Your ${formatInr(order.advance_amount)} deposit will be refunded.`
        : "Cancel this order?";
    if (window.confirm(msg)) act(() => api.post(`/bulk-orders/${id}/cancel`, {}));
  }

  if (error && !order) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">Loading order…</p>;

  const est = estimateSummary(order.estimate);
  const quoted = order.total_amount != null;
  const open = !["completed", "cancelled"].includes(order.status);
  const when = new Date(order.event_at + "Z");

  return (
    <div className="max-w-5xl mx-auto flex flex-col gap-6">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

      <header className="maroon-panel px-6 py-7 sm:px-10 sm:py-9 flex flex-col sm:flex-row gap-6 sm:items-center fade-up">
        <img src="/patterns/mandala.svg" alt="" aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 w-72 opacity-[0.22]" />
        <div className="relative flex-none w-20 rounded-xl overflow-hidden text-center bg-ivory-raised text-ink shadow-lg">
          <p className="bg-gold text-ivory-raised text-[11px] font-bold uppercase tracking-wider py-1">{when.toLocaleDateString(undefined, { month: "short" })}</p>
          <p className="font-display text-3xl font-semibold text-maroon leading-none pt-2">{when.getDate()}</p>
          <p className="text-[11px] text-ink-soft pb-2">{when.toLocaleDateString(undefined, { weekday: "short" })}</p>
        </div>
        <div className="relative flex-1 min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-gold-soft/80">Event order</p>
          <h1 className="font-display text-3xl font-semibold text-ivory-raised leading-tight">{bulkOccasionLabel(order.occasion)}</h1>
          <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm text-gold-soft">
            <span className="flex items-center gap-1.5">
              <Icon name="people" className="w-4 h-4" /> {order.people} {order.people === 1 ? "person" : "people"}
            </span>
            <span className="flex items-center gap-1.5">
              <Icon name="calendar" className="w-4 h-4" /> {when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
            </span>
            <span className="flex items-center gap-1.5 min-w-0">
              <Icon name="pin" className="w-4 h-4 flex-none" /> <span className="truncate">{order.address_text}</span>
            </span>
          </div>
        </div>
        {order.advance_amount > 0 && (
          <span className="relative self-start chip bg-ivory-raised/15 text-gold-soft ring-1 ring-gold-soft/40">{DEPOSIT_LABELS[order.advance_status]}</span>
        )}
      </header>

      <div className="card px-4 py-5 sm:px-8">
        <StatusTracker status={order.status} />
      </div>

      <div className="grid lg:grid-cols-[1fr_21rem] gap-6 items-start">
        <section className="flex flex-col gap-4">
          <h2 className="text-xl text-maroon">Who&apos;s getting mehndi</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {order.lines.map((l) => {
              const img = l.design_image_url || l.reference_image_url;
              return (
                <div key={l.id} className="card overflow-hidden flex flex-col fade-up">
                  <div className="relative h-36 bg-ivory overflow-hidden">
                    {img ? (
                      <img src={img} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <img src="/patterns/mandala.svg" alt="" className="absolute inset-0 m-auto w-32 opacity-25" />
                    )}
                    <span className="absolute bottom-2 left-2 rounded-full bg-maroon text-ivory-raised text-sm font-display font-semibold px-3 py-0.5 shadow">
                      × {l.quantity}
                    </span>
                    {l.reference_image_url && <span className="absolute top-2 right-2 chip bg-ivory-raised shadow">Your design</span>}
                  </div>
                  <div className="p-4 flex flex-col gap-1 text-sm">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gold">{categoryLabel(l.category)}</span>
                    <p className="font-semibold leading-tight">{l.design_name || l.package_name}</p>
                    {l.note && <p className="text-xs text-ink-soft italic">“{l.note}”</p>}
                    <p className="text-xs mt-1">
                      {l.unit_price != null ? (
                        <>
                          <b className="text-maroon">{formatInr(l.unit_price)}</b> per person
                          <span className="text-ink-soft"> · range {formatPriceRange(l.unit_price_min, l.unit_price_max)}</span>
                        </>
                      ) : (
                        <span className="font-semibold text-maroon-soft">{formatPriceRange(l.unit_price_min, l.unit_price_max)} per person</span>
                      )}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
          {order.notes && (
            <div className="card p-4 text-sm">
              <p className="text-[11px] font-bold uppercase tracking-wider text-gold mb-1">Your notes</p>
              <p>“{order.notes}”</p>
            </div>
          )}
        </section>

        <aside className="lg:sticky lg:top-24 flex flex-col gap-4">
          <Receipt
            title={quoted ? "Your quote" : "Your estimate"}
            subtitle={quoted ? `Inside your estimate of ${est.total}` : "Our team is lining up artists for you"}
            rows={
              quoted
                ? [
                    ["Mehndi", formatInr(order.subtotal)],
                    ["Platform fee", formatInr(order.platform_fee)],
                  ]
                : [
                    ["Mehndi", est.subtotal],
                    ["Platform fee", est.fee],
                  ]
            }
            total={[quoted ? "Total" : "Estimated", quoted ? formatInr(order.total_amount) : est.total]}
            footnotes={[
              quoted ? "Every person is priced within their usual range." : "We'll send a quote inside this range — never above it.",
              order.advance_amount > 0 && `${formatInr(order.advance_amount)} deposit, paid in-app once you accept and counted towards your total. The balance is paid on the event day.`,
            ]}
          >
            {order.admin_note && (
              <div className="mt-4 rounded-lg bg-gold-soft px-3 py-2 text-xs">
                <p className="font-bold text-maroon mb-0.5">Note from our team</p>
                {order.admin_note}
              </div>
            )}
            {order.cancel_reason && <p className="mt-3 text-xs text-ink-soft">Cancelled: {order.cancel_reason}</p>}
            {error && <p className="text-sm text-red-700 mt-3">{error}</p>}
            {order.status === "quoted" && (
              <button className="btn-primary w-full mt-4 py-3" disabled={busy} onClick={() => act(() => api.post(`/bulk-orders/${id}/accept`, {}))}>
                Accept quote · {formatInr(order.total_amount)}
              </button>
            )}
            {order.status === "confirmed" && order.advance_status === "pending" && (
              <button className="btn-primary w-full mt-4 py-3" disabled={busy} onClick={payDeposit}>
                Pay {formatInr(order.advance_amount)} deposit
              </button>
            )}
            {open && (
              <button className="w-full mt-2 text-xs text-ink-soft hover:text-red-700 underline" disabled={busy} onClick={cancel}>
                {order.status === "quoted" ? "Decline & cancel order" : "Cancel order"}
              </button>
            )}
          </Receipt>
          <PricePromise compact />
        </aside>
      </div>

      <Link href="/my-bookings" className="text-sm text-maroon-soft underline self-start">
        ← All my bookings &amp; event orders
      </Link>
    </div>
  );
}
