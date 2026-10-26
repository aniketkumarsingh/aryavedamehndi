import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { api } from "@/lib/api";
import { BUSINESS } from "@/lib/business";
import { canTaxInvoice, gstLines } from "@/lib/gst";

const INVOICEABLE = ["paid", "shipped", "delivered"];
const money = (n) => `₹${Number(n).toFixed(2)}`;

/** Printable receipt for a paid shop order. Becomes a GST tax invoice once
 * the seller's GSTIN and state, and every product's GST rate, are set. */
export default function Invoice() {
  const router = useRouter();
  const { id } = router.query;
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api.get(`/shop/orders/${id}`).then(setOrder).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!order) return <p className="text-ink-soft">Loading…</p>;
  if (!INVOICEABLE.includes(order.status)) {
    return (
      <p className="text-ink-soft">
        A receipt is available once the order is paid. <Link href={`/shop/orders/${id}`} className="underline">Back to order</Link>
      </p>
    );
  }

  const taxInvoice = canTaxInvoice(order, BUSINESS);
  const gst = taxInvoice ? gstLines(order, BUSINESS) : null;
  const title = taxInvoice ? "Tax Invoice" : "Order Receipt";
  const date = new Date(order.paid_at || order.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-4">
      <Head>
        <title>{`${title} ${order.invoice_number || ""} — AryaVeda Mehndi`}</title>
      </Head>
      <div className="flex justify-between items-center no-print">
        <Link href={`/shop/orders/${id}`} className="text-sm text-maroon-soft underline">← Back to order</Link>
        <button className="btn-primary text-sm" onClick={() => window.print()}>Print / Save as PDF</button>
      </div>

      <div className="card p-6 flex flex-col gap-5 print-plain">
        <div className="flex justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl">{title}</h1>
            <p className="text-sm">No. <b>{order.invoice_number || order.id.slice(0, 8).toUpperCase()}</b> · {date}</p>
          </div>
          <div className="text-sm text-right">
            <p className="font-semibold">{BUSINESS.legalName || "AryaVeda Mehndi"}</p>
            {BUSINESS.address && <p className="text-ink-soft whitespace-pre-line">{BUSINESS.address}</p>}
            {BUSINESS.state && <p className="text-ink-soft">State: {BUSINESS.state}</p>}
            {BUSINESS.gstin && <p>GSTIN: {BUSINESS.gstin}</p>}
          </div>
        </div>

        <div className="text-sm">
          <p className="font-semibold">Bill / ship to</p>
          <p>{order.shipping_name} · {order.shipping_phone}</p>
          <p className="text-ink-soft whitespace-pre-line">{order.shipping_address}</p>
          {(order.shipping_state || order.shipping_pincode) && (
            <p className="text-ink-soft">{[order.shipping_state, order.shipping_pincode].filter(Boolean).join(" - ")}</p>
          )}
          {taxInvoice && <p className="text-ink-soft">Place of supply: {order.shipping_state || "—"}</p>}
        </div>

        {taxInvoice ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="py-1 pr-2">Item</th>
                  <th className="py-1 pr-2">HSN</th>
                  <th className="py-1 pr-2 text-right">Qty</th>
                  <th className="py-1 pr-2 text-right">Taxable value</th>
                  <th className="py-1 pr-2 text-right">GST %</th>
                  {gst.intraState ? (
                    <>
                      <th className="py-1 pr-2 text-right">CGST</th>
                      <th className="py-1 pr-2 text-right">SGST</th>
                    </>
                  ) : (
                    <th className="py-1 pr-2 text-right">IGST</th>
                  )}
                  <th className="py-1 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {gst.lines.map((l, i) => (
                  <tr key={i} className="border-b border-line">
                    <td className="py-1 pr-2">{l.description}</td>
                    <td className="py-1 pr-2">{l.hsn}</td>
                    <td className="py-1 pr-2 text-right">{l.quantity}</td>
                    <td className="py-1 pr-2 text-right">{money(l.taxable)}</td>
                    <td className="py-1 pr-2 text-right">{l.rate}%</td>
                    {gst.intraState ? (
                      <>
                        <td className="py-1 pr-2 text-right">{money(l.cgst)}</td>
                        <td className="py-1 pr-2 text-right">{money(l.sgst)}</td>
                      </>
                    ) : (
                      <td className="py-1 pr-2 text-right">{money(l.igst)}</td>
                    )}
                    <td className="py-1 text-right">{money(l.total)}</td>
                  </tr>
                ))}
                <tr className="font-semibold">
                  <td className="py-1 pr-2" colSpan={3}>Total</td>
                  <td className="py-1 pr-2 text-right">{money(gst.totals.taxable)}</td>
                  <td />
                  {gst.intraState ? (
                    <>
                      <td className="py-1 pr-2 text-right">{money(gst.totals.cgst)}</td>
                      <td className="py-1 pr-2 text-right">{money(gst.totals.sgst)}</td>
                    </>
                  ) : (
                    <td className="py-1 pr-2 text-right">{money(gst.totals.igst)}</td>
                  )}
                  <td className="py-1 text-right">{money(gst.totals.total)}</td>
                </tr>
              </tbody>
            </table>
            {order.discount_amount > 0 && (
              <p className="text-xs text-ink-soft mt-2">Includes coupon {order.coupon_code} discount of {money(order.discount_amount)}, shared across items by value.</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-1 text-sm">
            {order.items.map((i) => (
              <div key={`${i.product_id}:${i.variant_id || ""}`} className="flex justify-between border-b border-line pb-1">
                <span>
                  {i.product_name}{i.variant_label ? ` (${i.variant_label})` : ""} × {i.quantity}
                </span>
                <span>{money(i.subtotal)}</span>
              </div>
            ))}
            {order.discount_amount > 0 && (
              <div className="flex justify-between"><span>Coupon {order.coupon_code}</span><span>−{money(order.discount_amount)}</span></div>
            )}
            <div className="flex justify-between"><span>Delivery</span><span>{order.shipping_fee > 0 ? money(order.shipping_fee) : "Free"}</span></div>
            <div className="flex justify-between font-semibold border-t border-line pt-1"><span>Total paid (incl. taxes)</span><span>{money(order.total_amount)}</span></div>
          </div>
        )}

        <div className="text-xs text-ink-soft flex flex-col gap-1">
          <p>Paid online{order.paid_at ? ` on ${date}` : ""}. Prices include all taxes.</p>
          {order.status === "cancelled" && <p>This order was cancelled.</p>}
          <p>This is a computer-generated document and does not need a signature.</p>
        </div>
      </div>
    </div>
  );
}
