import { beforeEach, describe, test } from "node:test";
import assert from "node:assert/strict";

// Minimal browser globals for src/lib/attribution.js.
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.window = { location: { href: "", origin: "https://www.aryavedamehndi.com" } };
globalThis.document = { referrer: "", cookie: "" };

const { attributionPayload, captureLanding, firstTouch } = await import("../src/lib/attribution.js");

function land(url, referrer = "") {
  window.location.href = url;
  document.referrer = referrer;
  captureLanding();
}

beforeEach(() => {
  store.clear();
  document.cookie = "";
});

describe("attribution", () => {
  test("keeps the first touch and updates the latest", () => {
    land("https://www.aryavedamehndi.com/shop?utm_source=instagram&utm_campaign=diwali");
    land("https://www.aryavedamehndi.com/designs?utm_source=google&gclid=xyz");
    assert.equal(firstTouch().utm_source, "instagram");
    const last = attributionPayload();
    assert.equal(last.utm_source, "google");
    assert.equal(last.gclid, "xyz");
    assert.equal(last.landing_path, "/designs");
  });

  test("plain internal visits change nothing; a referral code sticks", () => {
    land("https://www.aryavedamehndi.com/?ref=priya1234");
    land("https://www.aryavedamehndi.com/shop");
    land("https://www.aryavedamehndi.com/shop?utm_source=newsletter");
    const last = attributionPayload();
    assert.equal(last.ref, "PRIYA1234");
    assert.equal(last.utm_source, "newsletter");
  });

  test("ad cookies are read only with analytics consent", () => {
    land("https://www.aryavedamehndi.com/?utm_source=meta");
    document.cookie = "_ga=GA1.1.123456.789; _fbp=fb.1.1.42";
    assert.equal(attributionPayload().ga_client_id, undefined);
    localStorage.setItem("aryaveda_consent", "granted");
    const out = attributionPayload();
    assert.equal(out.ga_client_id, "123456.789");
    assert.equal(out.fbp, "fb.1.1.42");
  });

  test("an old latest touch is dropped after 30 days", () => {
    land("https://www.aryavedamehndi.com/?utm_source=old");
    const last = JSON.parse(localStorage.getItem("aryaveda_last_touch"));
    last.captured_at = new Date(Date.now() - 31 * 864e5).toISOString();
    localStorage.setItem("aryaveda_last_touch", JSON.stringify(last));
    assert.equal(attributionPayload(), null);
  });
});
