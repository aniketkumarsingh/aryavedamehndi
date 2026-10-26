import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/download";

const money = (n) => `₹${Number(n).toFixed(2)}`;

/** The order's receipt, or its GST tax invoice once dispatched. The
 * document is built on the server (app/services/documents.py), so this
 * page, the PDF and the emailed copy always agree. */
export default function Invoice() {
  const router = useRouter();
  const { id } = router.query;
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api.get(`/shop/orders/${id}/document`).then(setDoc).catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <p className="text-ink-soft">
        {error} <Link href={`/shop/orders/${id}`} className="underline">Back to order</Link>
      </p>
    );
  }
  if (!doc) return <p className="text-ink-soft">Loading…</p>;

  const { seller, buyer, taxed, intra_state: intra, totals } = doc;

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-4">
      <Head>
        <title>{`${doc.title} ${doc.number} — AryaVeda Mehndi`}</title>
      </Head>
      <div className="flex justify-between items-center gap-2 no-print flex-wrap">
        <Link href={`/shop/orders/${id}`} className="text-sm text-maroon-soft underline">← Back to order</Link>
        <div className="flex gap-2">
          <button className="btn-secondary text-sm" onClick={() => window.print()}>Print</button>
          <button className="btn-primary text-sm" onClick={() => downloadFile(`/shop/orders/${id}/document.pdf`, `${doc.number.replace(/\s+/g, "-")}.pdf`).catch((e) => setError(e.message))}>
            Download PDF
          </button>
        </div>
      </div>

      <div className="card p-6 flex flex-col gap-5 print-plain">
        <div className="flex justify-between gap-4 flex-wrap border-b-2 border-maroon pb-3">
          <div>
            <h1 className="text-2xl">{doc.title}</h1>
            <p className="text-sm">No. <b>{doc.number}</b> · {doc.date}</p>
          </div>
          <div className="text-sm sm:text-right">
            <p className="font-semibold">{seller.name}</p>
            {seller.address && <p className="text-ink-soft whitespace-pre-line">{seller.address}</p>}
            {seller.state && <p className="text-ink-soft">State: {seller.state}</p>}
            {seller.gstin && <p>GSTIN: {seller.gstin}</p>}
          </div>
        </div>

        <div className="text-sm">
          <p className="font-semibold">Bill / ship to</p>
          <p>{buyer.name} · {buyer.phone}</p>
          <p className="text-ink-soft whitespace-pre-line">{buyer.address}</p>
          {(buyer.state || buyer.pincode) && <p className="text-ink-soft">{[buyer.state, buyer.pincode].filter(Boolean).join(" - ")}</p>}
          {taxed && <p className="text-ink-soft">Place of supply: {doc.place_of_supply || "—"} · Prices include GST</p>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="py-1 pr-2">Item</th>
                {taxed && <th className="py-1 pr-2">HSN</th>}
                <th className="py-1 pr-2 text-right">Qty</th>
                {taxed ? (
                  <>
                    <th className="py-1 pr-2 text-right">Taxable value</th>
                    <th className="py-1 pr-2 text-right">GST %</th>
                    {intra ? (
                      <>
                        <th className="py-1 pr-2 text-right">CGST</th>
                        <th className="py-1 pr-2 text-right">SGST</th>
                      </>
                    ) : (
                      <th className="py-1 pr-2 text-right">IGST</th>
                    )}
                  </>
                ) : (
                  <th className="py-1 pr-2 text-right">Unit price</th>
                )}
                <th className="py-1 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {doc.lines.map((l, i) => (
                <tr key={i} className="border-b border-line">
                  <td className="py-1 pr-2">{l.description}</td>
                  {taxed && <td className="py-1 pr-2">{l.hsn}</td>}
                  <td className="py-1 pr-2 text-right">{l.quantity}</td>
                  {taxed ? (
                    <>
                      <td className="py-1 pr-2 text-right">{money(l.taxable)}</td>
                      <td className="py-1 pr-2 text-right">{l.rate}%</td>
                      {intra ? (
                        <>
                          <td className="py-1 pr-2 text-right">{money(l.cgst)}</td>
                          <td className="py-1 pr-2 text-right">{money(l.sgst)}</td>
                        </>
                      ) : (
                        <td className="py-1 pr-2 text-right">{money(l.igst)}</td>
                      )}
                    </>
                  ) : (
                    <td className="py-1 pr-2 text-right">{money(l.unit_price)}</td>
                  )}
                  <td className="py-1 text-right">{money(l.total)}</td>
                </tr>
              ))}
              <tr className="font-semibold">
                <td className="py-1 pr-2" colSpan={taxed ? 3 : 3}>Total</td>
                {taxed && (
                  <>
                    <td className="py-1 pr-2 text-right">{money(totals.taxable)}</td>
                    <td />
                    {intra ? (
                      <>
                        <td className="py-1 pr-2 text-right">{money(totals.cgst)}</td>
                        <td className="py-1 pr-2 text-right">{money(totals.sgst)}</td>
                      </>
                    ) : (
                      <td className="py-1 pr-2 text-right">{money(totals.igst)}</td>
                    )}
                  </>
                )}
                <td className="py-1 text-right">{money(totals.total)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="text-xs text-ink-soft flex flex-col gap-1">
          <p><b>Amount in words:</b> {doc.amount_in_words}</p>
          {doc.discount && <p>Includes coupon {doc.discount.code} discount of {money(doc.discount.amount)}, shared across items by value.</p>}
          {doc.payment.method === "cod" ? (
            <p>Payment: Cash on Delivery{doc.payment.status === "cod_collected" ? " — collected." : " — to be paid at delivery."}</p>
          ) : (
            <p>
              Paid online: {money(doc.payment.paid)}
              {doc.payment.reference ? ` (ref. ${doc.payment.reference})` : ""}
              {doc.payment.refunded ? ` · Refunded: ${money(doc.payment.refunded)}` : ""}
            </p>
          )}
          {doc.kind === "receipt" && <p>Your GST invoice is issued when the order ships.</p>}
          <p>This is a computer-generated document and does not require a signature.</p>
        </div>
      </div>
    </div>
  );
}
