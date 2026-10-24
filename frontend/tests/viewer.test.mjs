import { test } from "node:test";
import assert from "node:assert/strict";

import { clampPan, pinchZoom, swipeDirection, tiltFromOrientation, tiltFromPointer, zoomAt } from "../src/lib/viewer.js";

const rect = { left: 100, top: 50, width: 400, height: 400 };

test("pointer tilt leans toward the pointer and is flat at the centre", () => {
  assert.deepEqual(tiltFromPointer(300, 250, rect), { rx: 0, ry: 0 });
  assert.deepEqual(tiltFromPointer(500, 250, rect), { rx: 0, ry: 16 });
  assert.deepEqual(tiltFromPointer(300, 50, rect), { rx: 16, ry: 0 });
  assert.deepEqual(tiltFromPointer(9999, -9999, rect), { rx: 16, ry: 16 }, "clamped at the edges");
});

test("phone tilt is relative to the starting angle and clamped", () => {
  const base = { beta: 40, gamma: 0 };
  assert.deepEqual(tiltFromOrientation(40, 0, base), { rx: 0, ry: 0 });
  assert.deepEqual(tiltFromOrientation(40, 12.5, base), { rx: 0, ry: 8 });
  assert.deepEqual(tiltFromOrientation(140, -90, base), { rx: -16, ry: -16 });
});

test("pan never uncovers the frame", () => {
  assert.deepEqual(clampPan({ x: 500, y: -500 }, 2, 400, 400), { x: 200, y: -200 });
  assert.deepEqual(clampPan({ x: 50, y: 50 }, 1, 400, 400), { x: 0, y: 0 });
});

test("zooming keeps the point under the cursor in place", () => {
  const next = zoomAt({ zoom: 1, pan: { x: 0, y: 0 } }, 2, { x: 100, y: 0 }, 400, 400);
  assert.equal(next.zoom, 2);
  assert.deepEqual(next.pan, { x: -100, y: 0 });
  // Zooming back out to 1x recentres.
  assert.deepEqual(zoomAt(next, 0.5, { x: 0, y: 0 }, 400, 400), { zoom: 1, pan: { x: 0, y: 0 } });
  assert.equal(zoomAt(next, 50, { x: 0, y: 0 }, 400, 400).zoom, 5, "capped at max zoom");
});

test("pinch scales from the starting zoom", () => {
  assert.equal(pinchZoom(1, 100, 250), 2.5);
  assert.equal(pinchZoom(2, 100, 10), 1);
  assert.equal(pinchZoom(2, 0, 100), 2);
});

test("only clearly horizontal drags swipe", () => {
  assert.equal(swipeDirection(-80, 5), 1);
  assert.equal(swipeDirection(80, 5), -1);
  assert.equal(swipeDirection(30, 0), 0);
  assert.equal(swipeDirection(-80, 70), 0);
});

import { maxZoomFor, spinFrameFromDrag } from "../src/lib/viewer.js";

test("zoom stops where the photo runs out of real detail", () => {
  // 1024px photo in a 688px frame on a 2x screen: already below native at 100%.
  assert.equal(maxZoomFor(1024, 688, 2), 1);
  // 4096px upscaled photo, same frame and screen: ~2.98x native, 3.72x with headroom.
  assert.equal(maxZoomFor(4096, 688, 2), 3.72);
  // Very large image on a 1x screen is capped at the viewer max.
  assert.equal(maxZoomFor(8000, 600, 1), 5);
  assert.equal(maxZoomFor(0, 600, 1), 1);
});

test("dragging the full width turns the 360 view once", () => {
  assert.equal(spinFrameFromDrag(0, 0, 600, 36), 0);
  assert.equal(spinFrameFromDrag(0, -600, 600, 36), 0, "full turn left returns to start");
  assert.equal(spinFrameFromDrag(0, -100, 600, 36), 6);
  assert.equal(spinFrameFromDrag(0, 100, 600, 36), 30, "wraps backwards");
  assert.equal(spinFrameFromDrag(35, -50, 600, 36), 2, "wraps forwards");
});
