const defaultRuntimeCaching = require("next-pwa/cache");

// Workbox uses the first matching rule, so these run before next-pwa's
// defaults. The default "apis" rule cached every /api/* GET (profile,
// bookings, notifications, admin data) for 24h - readable offline and after
// logout on a shared phone. Only public catalogue data is cached now.
const runtimeCaching = [
  {
    urlPattern: ({ url, sameOrigin }) => sameOrigin && /^\/api\/(cms|packages|shop\/products)(\/|$)/.test(url.pathname),
    handler: "NetworkFirst",
    method: "GET",
    options: {
      cacheName: "public-api",
      networkTimeoutSeconds: 5,
      expiration: { maxEntries: 32, maxAgeSeconds: 24 * 60 * 60 },
    },
  },
  {
    urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.startsWith("/api/"),
    handler: "NetworkOnly",
    options: {}, // next-pwa requires an options object on every rule
  },
  // KYC documents (Aadhaar/PAN/selfie) are served via short-lived signed
  // URLs - never keep a copy on the device.
  {
    urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.toLowerCase().startsWith("/media/kyc/"),
    handler: "NetworkOnly",
    options: {},
  },
  ...defaultRuntimeCaching,
];

const withPWA = require("next-pwa")({
  dest: "public",
  register: true,
  skipWaiting: true,
  runtimeCaching,
  // The service worker is off under `next dev` (it would cache stale dev
  // builds), which also means browsers won't offer to install the app in
  // dev - see "Testing the installable app" in the root README.
  disable: process.env.NODE_ENV === "development",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "127.0.0.1" },
    ],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase}/:path*` },
      // Uploaded photos (KYC, portfolio, designs) come back from the API as
      // "/media/..." paths - proxy them too so they resolve against this
      // origin instead of 404ing against the frontend's own server.
      { source: "/media/:path*", destination: `${apiBase}/media/:path*` },
    ];
  },
};

module.exports = withPWA(nextConfig);
