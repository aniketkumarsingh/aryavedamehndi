import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { detectPlatform } from "../src/lib/pwa.js";

const UA = {
  iphoneSafari: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  iphoneChrome: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.0.0 Mobile/15E148 Safari/604.1",
  ipadSafari: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
  macSafari: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
  macChrome: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  winEdge: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
  androidChrome: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
  androidSamsung: "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36",
  winFirefox: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
};

test("detects OS and browser for each install path", () => {
  assert.deepEqual(detectPlatform(UA.iphoneSafari, 5), { os: "ios", browser: "safari" });
  assert.deepEqual(detectPlatform(UA.iphoneChrome, 5), { os: "ios", browser: "chrome" });
  assert.deepEqual(detectPlatform(UA.macSafari, 0), { os: "mac", browser: "safari" });
  assert.deepEqual(detectPlatform(UA.macChrome, 0), { os: "mac", browser: "chrome" });
  assert.deepEqual(detectPlatform(UA.winEdge, 0), { os: "windows", browser: "edge" });
  assert.deepEqual(detectPlatform(UA.androidChrome, 5), { os: "android", browser: "chrome" });
  assert.deepEqual(detectPlatform(UA.androidSamsung, 5), { os: "android", browser: "samsung" });
  assert.deepEqual(detectPlatform(UA.winFirefox, 0), { os: "windows", browser: "firefox" });
});

test("iPadOS Safari (desktop user agent) is treated as iOS via touch points", () => {
  assert.equal(detectPlatform(UA.ipadSafari, 5).os, "ios");
});

test("manifest has the fields browsers need to install the app", () => {
  const manifest = JSON.parse(readFileSync(new URL("../public/manifest.json", import.meta.url)));
  for (const key of ["id", "name", "short_name", "start_url", "scope", "display", "icons"]) {
    assert.ok(manifest[key], `manifest.${key} missing`);
  }
  assert.equal(manifest.display, "standalone");
  const any = manifest.icons.filter((i) => i.purpose === "any").map((i) => i.sizes);
  const maskable = manifest.icons.filter((i) => i.purpose === "maskable").map((i) => i.sizes);
  assert.deepEqual(any.sort(), ["192x192", "512x512"]);
  assert.deepEqual(maskable.sort(), ["192x192", "512x512"]);
  for (const icon of manifest.icons) {
    readFileSync(new URL(`../public${icon.src}`, import.meta.url)); // throws if missing
  }
});
