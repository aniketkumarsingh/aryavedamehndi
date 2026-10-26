// GST breakdown for a shop order, for the printable invoice. Shop prices
// are MRPs that already include GST, so tax is worked backwards from each
// line's price after its share of any coupon discount. Delivery is taxed
// at the order's highest item rate (mixed supply). Have an accountant
// confirm HSN codes, rates and this treatment before relying on it.

const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

/** Whether a proper tax invoice can be produced: seller GSTIN + state, and
 * a GST rate on every line. Otherwise the page shows a plain receipt. */
export function canTaxInvoice(order, seller) {
  return Boolean(seller.gstin && seller.state && order.items.length && order.items.every((i) => i.gst_rate != null));
}

export function gstLines(order, seller) {
  const intraState = Boolean(order.shipping_state) && order.shipping_state.trim().toLowerCase() === seller.state.trim().toLowerCase();
  const itemsAmount = order.items_amount ?? order.items.reduce((s, i) => s + i.subtotal, 0);
  const discount = order.discount_amount || 0;

  const split = (inclusive, rate) => {
    const taxable = round2(inclusive / (1 + rate / 100));
    const tax = round2(inclusive - taxable);
    return intraState
      ? { taxable, cgst: round2(tax / 2), sgst: round2(tax - round2(tax / 2)), igst: 0 }
      : { taxable, cgst: 0, sgst: 0, igst: tax };
  };

  const lines = order.items.map((i) => {
    const share = itemsAmount > 0 ? (discount * i.subtotal) / itemsAmount : 0;
    const inclusive = round2(i.subtotal - share);
    return {
      description: `${i.product_name}${i.variant_label ? ` (${i.variant_label})` : ""}`,
      hsn: i.hsn_code || "",
      quantity: i.quantity,
      rate: i.gst_rate,
      total: inclusive,
      ...split(inclusive, i.gst_rate),
    };
  });
  if (order.shipping_fee > 0) {
    const rate = Math.max(...order.items.map((i) => i.gst_rate));
    lines.push({ description: "Delivery charges", hsn: "", quantity: 1, rate, total: order.shipping_fee, ...split(order.shipping_fee, rate) });
  }

  const sum = (k) => round2(lines.reduce((s, l) => s + l[k], 0));
  return { intraState, lines, totals: { taxable: sum("taxable"), cgst: sum("cgst"), sgst: sum("sgst"), igst: sum("igst"), total: sum("total") } };
}
