import { test } from "node:test";
import assert from "node:assert/strict";

import { categoryLabel, formatDuration, formatPriceRange, groupByCategory } from "../src/lib/designs.js";

test("price ranges use Indian digit grouping and collapse equal ends", () => {
  assert.equal(formatPriceRange(2500, 4000), "₹2,500 – ₹4,000");
  assert.equal(formatPriceRange(150000, 250000), "₹1,50,000 – ₹2,50,000");
  assert.equal(formatPriceRange(800, 800), "₹800");
});

test("durations read naturally", () => {
  assert.equal(formatDuration(45), "45 min");
  assert.equal(formatDuration(60), "1 hr");
  assert.equal(formatDuration(150), "2 hr 30 min");
});

test("categories group in display order, unknown ones last", () => {
  const designs = [
    { id: 1, category: "feet" },
    { id: 2, category: "mystery" },
    { id: 3, category: "bridal" },
    { id: 4, category: "feet" },
  ];
  assert.deepEqual(
    groupByCategory(designs).map(([cat, items]) => [cat, items.map((d) => d.id)]),
    [["bridal", [3]], ["feet", [1, 4]], ["mystery", [2]]]
  );
  assert.equal(categoryLabel("party"), "Party & Festive");
  assert.equal(categoryLabel("regular"), "Simple & Daily");
  assert.equal(categoryLabel("mystery"), "Mystery");
});

test("filterDesigns applies every filter that is set", async () => {
  const { filterDesigns, optionsPresent, STYLES, OCCASIONS, coverageLabel, occasionLabel } = await import("../src/lib/designs.js");
  const designs = [
    { id: "a", category: "party", style: "arabic", coverage: "back", occasions: ["eid", "party"] },
    { id: "b", category: "regular", style: "arabic", coverage: "palm", occasions: ["everyday"] },
    { id: "c", category: "party", style: "mandala", coverage: "back", occasions: ["diwali"] },
  ];
  const ids = (f) => filterDesigns(designs, f).map((d) => d.id);
  assert.deepEqual(ids({}), ["a", "b", "c"]);
  assert.deepEqual(ids({ category: "all", style: "arabic" }), ["a", "b"]);
  assert.deepEqual(ids({ category: "party", coverage: "back", occasion: "diwali" }), ["c"]);
  assert.deepEqual(ids({ occasion: "teej" }), []);
  assert.deepEqual(optionsPresent(designs, STYLES, "style").map((o) => o.key), ["arabic", "mandala"]);
  assert.deepEqual(optionsPresent(designs, OCCASIONS, "occasions").map((o) => o.key), ["party", "everyday", "eid", "diwali"]);
  assert.equal(coverageLabel("forearm"), "Past the wrist");
  assert.equal(occasionLabel("karwa-chauth"), "Karwa Chauth");
});
