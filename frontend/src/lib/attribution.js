// Where visitors come from: UTM tags, ad click ids and ?ref= referral codes
// from the landing URL. The first touch is kept for good; the latest one is
// sent with each order, booking and bulk request (see app/services/attribution.py).
// Ad cookies (_fbp, _fbc, _ga) are only read once analytics consent is given.
import { getConsent } from "./analytics.js";

const FIRST_KEY = "aryaveda_first_touch";
const LAST_KEY = "aryaveda_last_touch";
const PARAMS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid", "ref"];
const LAST_TOUCH_DAYS = 30;

function read(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage blocked - attribution just isn't remembered */
  }
}

/** Called once per page load: records the landing if it carries campaign data. */
export function captureLanding() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const touch = {};
  for (const p of PARAMS) {
    const v = url.searchParams.get(p);
    if (v) touch[p] = v.slice(0, 150);
  }
  const external = document.referrer && !document.referrer.startsWith(window.location.origin);
  if (!Object.keys(touch).length && !external) return;
  if (external) touch.referrer = document.referrer.slice(0, 300);
  touch.landing_path = url.pathname.slice(0, 300);
  touch.captured_at = new Date().toISOString();
  if (touch.ref) touch.ref = touch.ref.toUpperCase().slice(0, 16);
  if (!read(FIRST_KEY)) write(FIRST_KEY, touch);
  const last = read(LAST_KEY);
  // Keep a known referral code even if a later visit has none.
  write(LAST_KEY, { ...(last?.ref && !touch.ref ? { ref: last.ref } : {}), ...touch });
}

function cookie(name) {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

/** The latest touch (within 30 days) plus ad cookies when consented. */
export function attributionPayload() {
  if (typeof window === "undefined") return null;
  let last = read(LAST_KEY);
  if (last?.captured_at && Date.now() - Date.parse(last.captured_at) > LAST_TOUCH_DAYS * 864e5) last = null;
  const out = { ...(last || {}) };
  if (getConsent() === "granted") {
    const ga = cookie("_ga"); // GA1.1.<client id>
    if (ga) out.ga_client_id = ga.split(".").slice(-2).join(".");
    if (cookie("_fbp")) out.fbp = cookie("_fbp");
    if (cookie("_fbc")) out.fbc = cookie("_fbc");
  }
  return Object.keys(out).length ? out : null;
}

export function firstTouch() {
  return read(FIRST_KEY);
}
