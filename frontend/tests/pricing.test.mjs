import { test } from "node:test";
import assert from "node:assert/strict";

import { BULK_OCCASIONS, estimateSummary, feeLabel, pricePromises } from "../src/lib/pricing.js";

test("fee label follows the admin's fee mode, always per person", () => {
  assert.equal(feeLabel({ platform_fee_mode: "percent", platform_fee_percent: 10, platform_fee_flat: 0 }), "10% of each person's price");
  assert.equal(feeLabel({ platform_fee_mode: "flat", platform_fee_percent: 10, platform_fee_flat: 1499 }), "₹1,499 per person");
  assert.match(feeLabel(null), /per person/);
});

test("every order page makes the same three promises", () => {
  const promises = pricePromises(null);
  assert.equal(promises.length, 3);
  assert.match(promises[0].body, /no bulk markup/i);
});

test("estimate summary formats ranges and hides a zero deposit", () => {
  const s = estimateSummary({
    people: 21,
    subtotal_min: 14000,
    subtotal_max: 36000,
    platform_fee_min: 1400,
    platform_fee_max: 3600,
    total_min: 15400,
    total_max: 39600,
    advance_amount: 0,
  });
  assert.equal(s.total, "₹15,400 – ₹39,600");
  assert.equal(s.deposit, null);
  assert.equal(estimateSummary(null), null);
});

test("bulk occasions have unique keys and lead with the mehndi ceremony", () => {
  const keys = BULK_OCCASIONS.map((o) => o.key);
  assert.equal(new Set(keys).size, keys.length);
  assert.equal(keys[0], "mehndi-ceremony");
});
