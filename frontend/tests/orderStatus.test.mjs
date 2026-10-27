import { describe, test } from "node:test";
import assert from "node:assert/strict";

const { orderSummaryLabel, statusLabel } = await import("../src/lib/orderStatus.js");

describe("statusLabel", () => {
  test("English, Hindi, and fallbacks", () => {
    assert.equal(statusLabel("shipment", "out_for_delivery"), "Out for delivery");
    assert.equal(statusLabel("shipment", "out_for_delivery", "hi"), "डिलीवरी के लिए निकला");
    assert.equal(statusLabel("reason", "damaged", "hi"), "ख़राब हालत में पहुँचा");
    assert.equal(statusLabel("shipment", "something_new", "hi"), "something_new");
  });

  test("order summary in Hindi", () => {
    assert.equal(orderSummaryLabel({ status: "cancelled", payment_status: "refunded" }, "hi"), "रद्द · रिफ़ंड हो गया");
    assert.equal(orderSummaryLabel({ status: "shipped", payment_status: "paid" }), "Shipped");
  });
});
