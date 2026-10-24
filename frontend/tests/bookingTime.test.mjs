import { test } from "node:test";
import assert from "node:assert/strict";

import { serviceWindow } from "../src/lib/bookingTime.js";

const MIN = 60000;
const base = { scheduled_at: "2026-11-01T10:00:00", package_duration_minutes: 120, status: "confirmed" };

test("no window without a package duration", () => {
  assert.equal(serviceWindow({ ...base, package_duration_minutes: null }), null);
});

test("before travel, the window starts at the scheduled time", () => {
  const { arrival, finish } = serviceWindow(base);
  assert.equal(arrival.getTime(), new Date(base.scheduled_at).getTime());
  assert.equal(finish - arrival, 120 * MIN);
});

test("en route, arrival follows the live ETA when it runs late", () => {
  const scheduled = new Date(base.scheduled_at).getTime();
  const now = scheduled - 5 * MIN; // 20 min ETA -> 15 min late
  const { arrival } = serviceWindow({ ...base, status: "artist_enroute", eta_minutes: 20 }, now);
  assert.equal(arrival.getTime(), now + 20 * MIN);
});

test("en route and early, arrival is never before the scheduled time", () => {
  const scheduled = new Date(base.scheduled_at).getTime();
  const { arrival } = serviceWindow({ ...base, status: "artist_enroute", eta_minutes: 10 }, scheduled - 60 * MIN);
  assert.equal(arrival.getTime(), scheduled);
});

test("after check-in, the actual (UTC) arrival time is used", () => {
  const { arrival, finish } = serviceWindow({ ...base, status: "in_progress", artist_arrived_at: "2026-11-01T04:40:00" });
  assert.equal(arrival.toISOString(), "2026-11-01T04:40:00.000Z");
  assert.equal(finish.toISOString(), "2026-11-01T06:40:00.000Z");
});
