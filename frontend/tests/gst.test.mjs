import { test } from "node:test";
import assert from "node:assert/strict";

import { canTaxInvoice, gstLines } from "../src/lib/gst.js";

const seller = { gstin: "07ABCDE1234F1Z5", state: "Delhi" };
const item = (subtotal, rate, extra = {}) => ({ product_name: "Henna", quantity: 1, subtotal, gst_rate: rate, hsn_code: "1404", ...extra });

test("needs GSTIN, seller state and a rate on every line", () => {
  const order = { items: [item(118, 18)] };
  assert.equal(canTaxInvoice(order, seller), true);
  assert.equal(canTaxInvoice(order, { ...seller, gstin: "" }), false);
  assert.equal(canTaxInvoice({ items: [item(118, 18), item(50, null)] }, seller), false);
});

test("same state splits tax into CGST + SGST from the inclusive price", () => {
  const order = { items: [item(118, 18)], items_amount: 118, discount_amount: 0, shipping_fee: 0, shipping_state: "delhi " };
  const { intraState, lines, totals } = gstLines(order, seller);
  assert.equal(intraState, true);
  assert.deepEqual([lines[0].taxable, lines[0].cgst, lines[0].sgst, lines[0].igst], [100, 9, 9, 0]);
  assert.equal(totals.total, 118);
});

test("other state uses IGST; discount is shared by value; delivery takes the highest rate", () => {
  const order = {
    items: [item(300, 18), item(100, 5)],
    items_amount: 400,
    discount_amount: 40,
    shipping_fee: 49,
    shipping_state: "Maharashtra",
  };
  const { intraState, lines, totals } = gstLines(order, seller);
  assert.equal(intraState, false);
  assert.equal(lines[0].total, 270); // 300 - 30
  assert.equal(lines[1].total, 90); // 100 - 10
  assert.equal(lines[2].description, "Delivery charges");
  assert.equal(lines[2].rate, 18);
  assert.equal(totals.total, 409); // what the customer paid
  assert.equal(totals.cgst + totals.sgst, 0);
  assert.equal(Math.round((totals.taxable + totals.igst) * 100) / 100, 409);
});
