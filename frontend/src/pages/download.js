import { useEffect, useState } from "react";
import { detectPlatform, isStandalone, useInstallPrompt } from "@/lib/pwa";

/** Install steps per platform/browser. Kept in sync with what the
 * browsers actually show as of late 2026 - menu labels drift, so each step
 * names the icon as well as the label. */
const STEPS = {
  android: {
    title: "Android",
    steps: [
      "Open this website in Chrome (Samsung Internet and Edge also work)",
      'Tap the menu (⋮) → "Add to Home screen" → "Install"',
      "The AryaVeda icon appears on your home screen and in your app drawer",
    ],
  },
  ios: {
    title: "iPhone / iPad",
    steps: [
      "Open this website in Safari (on iOS 16.4+, Chrome and Edge work too)",
      "Tap the Share icon (□↑) — at the bottom in Safari, in the address bar in Chrome",
      'Scroll down and tap "Add to Home Screen", then "Add"',
    ],
  },
  windows: {
    title: "Windows",
    steps: [
      "Open this website in Chrome or Edge",
      'Chrome: click the install icon (⊕) in the address bar, or menu (⋮) → "Cast, save and share" → "Install page as app". Edge: menu (…) → "Apps" → "Install this site as an app"',
      "The app opens in its own window and appears in the Start menu",
    ],
  },
  mac: {
    title: "Mac",
    steps: [
      "Open this website in Chrome, Edge, or Safari (Safari needs macOS Sonoma 14 or newer)",
      'Chrome/Edge: click the install icon (⊕) in the address bar. Safari: File menu → "Add to Dock…"',
      "Launch it from the Dock, Launchpad, or Spotlight",
    ],
  },
};

/** The one instruction that applies to the browser the visitor is using
 * right now, or null when the generic per-platform cards are enough. */
function stepsForThisBrowser({ os, browser }) {
  if (os === "ios") return STEPS.ios.steps;
  if (os === "mac" && browser === "safari") {
    return ['In the menu bar, choose File → "Add to Dock…" (macOS Sonoma 14 or newer)', 'Click "Add" — the app appears in your Dock'];
  }
  if (browser === "firefox") {
    return [
      os === "android"
        ? 'Tap the menu (⋮) → "Install" (or "Add to Home screen")'
        : "Firefox on computers can't install web apps — open this page in Chrome, Edge, or Safari (Mac) instead",
    ];
  }
  if (os === "android") return STEPS.android.steps;
  if (browser === "edge") return ['Open the menu (…) → "Apps" → "Install this site as an app"'];
  if (browser === "chrome") return ['Open the menu (⋮) → "Cast, save and share" → "Install page as app…"'];
  return null;
}

export default function DownloadApp() {
  const { canPrompt, installed, promptInstall } = useInstallPrompt();
  // Browser-only checks - rendered after mount so the static HTML matches.
  const [env, setEnv] = useState(null);
  const [outcome, setOutcome] = useState("");

  useEffect(() => {
    async function check() {
      const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : undefined;
      setEnv({
        platform: detectPlatform(),
        standalone: isStandalone(),
        secure: window.isSecureContext,
        hasServiceWorker: !!registration,
        origin: window.location.origin,
      });
    }
    check();
  }, []);

  async function install() {
    const result = await promptInstall();
    setOutcome(result === "accepted" ? "Installing… look for AryaVeda Mehndi on your home screen or app list." : "");
  }

  const localSteps = env ? stepsForThisBrowser(env.platform) : null;

  return (
    <div className="flex flex-col gap-8 max-w-2xl mx-auto">
      <div className="invitation-frame p-8 text-center flex flex-col items-center gap-3">
        <span className="corner-tl" aria-hidden="true" />
        <span className="corner-tr" aria-hidden="true" />
        <span className="corner-bl" aria-hidden="true" />
        <span className="corner-br" aria-hidden="true" />
        <img src="/logo/mark.svg" alt="" className="h-16 w-16" />
        <h1 className="text-2xl">Get the AryaVeda Mehndi App</h1>
        <p className="text-sm text-ink-soft max-w-sm">
          One app, every device — Android, iPhone, Windows or Mac. It installs straight from your browser in a few
          seconds, no app store needed.
        </p>

        {env?.standalone || installed ? (
          <p className="chip text-leaf">✓ The app is installed on this device</p>
        ) : canPrompt ? (
          <button type="button" className="btn-primary" onClick={install}>
            Install app
          </button>
        ) : null}
        {outcome && <p className="text-sm text-leaf">{outcome}</p>}
      </div>

      {env && !env.standalone && !installed && <SetupNotice env={env} />}

      {env && !env.standalone && !installed && !canPrompt && localSteps && (
        <div className="card p-5">
          <h2 className="font-semibold mb-3">Install on this device</h2>
          <ol className="flex flex-col gap-2 text-sm text-ink-soft list-decimal list-inside">
            {localSteps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
          {env.platform.browser !== "safari" && env.platform.os !== "ios" && (
            <p className="text-xs text-ink-soft mt-3">
              Don&apos;t see the option? The app may already be installed — check your apps list, or uninstall it there
              to reinstall.
            </p>
          )}
        </div>
      )}

      <div>
        <h2 className="font-semibold mb-3">On other devices</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          {Object.entries(STEPS).map(([key, p]) => (
            <PlatformCard key={key} title={p.title} steps={p.steps} highlight={env?.platform.os === key} />
          ))}
        </div>
      </div>

      <p className="text-xs text-ink-soft text-center">
        This installs a Progressive Web App — the same app you&apos;re using right now, with its own icon and window. Pages
        you&apos;ve already opened work offline; bookings, chat and payments need a connection. Updates install
        automatically.
      </p>
    </div>
  );
}

/** Explains why installing can't work here, instead of leaving the steps
 * to silently fail (no install icon ever appears in these cases). */
function SetupNotice({ env }) {
  if (!env.secure) {
    return (
      <div className="card p-5 border-l-4 border-red-700">
        <h2 className="font-semibold mb-1">Installing needs a secure (https) address</h2>
        <p className="text-sm text-ink-soft">
          You&apos;re on <b>{env.origin}</b>. Browsers only install apps from https sites (or from localhost on the same
          computer), so the install option won&apos;t appear here. Open the live https site instead.
        </p>
      </div>
    );
  }
  if (!env.hasServiceWorker && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return (
      <div className="card p-5 border-l-4 border-gold">
        <h2 className="font-semibold mb-1">Developer note: install is off in dev mode</h2>
        <p className="text-sm text-ink-soft">
          No service worker is running, which is expected under <code>npm run dev</code> — browsers won&apos;t offer to
          install without one. Run <code>npm run build &amp;&amp; npm start</code> to test installing. See &quot;Testing
          the installable app&quot; in the README for phones.
        </p>
      </div>
    );
  }
  return null;
}

function PlatformCard({ title, steps, highlight }) {
  return (
    <div className={`card p-5 ${highlight ? "ring-2 ring-gold" : ""}`}>
      <h3 className="font-semibold mb-3">
        {title}
        {highlight && <span className="chip ml-2 text-xs">this device</span>}
      </h3>
      <ol className="flex flex-col gap-2 text-sm text-ink-soft list-decimal list-inside">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
    </div>
  );
}
