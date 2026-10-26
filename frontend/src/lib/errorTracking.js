// Browser error tracking (Sentry). Off unless NEXT_PUBLIC_SENTRY_DSN is
// set at build time; NEXT_PUBLIC_GIT_SHA tags errors with the release.
// No personal data is sent (no IPs, no request bodies), and the SDK is
// loaded only when switched on, so it costs nothing otherwise.

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || "";
let started = false;

export async function initErrorTracking() {
  if (!DSN || started || typeof window === "undefined") return;
  started = true;
  const Sentry = await import("@sentry/browser");
  Sentry.init({
    dsn: DSN,
    release: process.env.NEXT_PUBLIC_GIT_SHA || undefined,
    environment: process.env.NODE_ENV,
    sendDefaultPii: false,
    // Errors from browser extensions and third-party scripts aren't ours.
    denyUrls: [/extensions\//i, /^chrome:\/\//i, /^moz-extension:\/\//i, /googletagmanager\.com/i, /connect\.facebook\.net/i],
  });
}
