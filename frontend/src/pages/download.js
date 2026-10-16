export default function DownloadApp() {
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
          One app, every device — Android, iPhone, Windows or Mac. Install it straight from your browser in a few
          seconds, no app store needed.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <PlatformCard
          title="Android"
          steps={[
            "Open this website in Chrome",
            'Tap the menu (⋮) → "Install app" (or look for the install icon in the address bar)',
            "Confirm — the app icon appears on your home screen",
          ]}
        />
        <PlatformCard
          title="iPhone / iPad"
          steps={[
            "Open this website in Safari",
            'Tap the Share icon (□↑) at the bottom',
            'Scroll down and tap "Add to Home Screen"',
          ]}
        />
        <PlatformCard
          title="Windows"
          steps={[
            "Open this website in Chrome or Edge",
            'Click the install icon (⊕) in the address bar, or menu → "Apps" → "Install this site as an app"',
            "The app opens in its own window from now on",
          ]}
        />
        <PlatformCard
          title="Mac"
          steps={[
            "Open this website in Chrome, Edge or Safari",
            'Chrome/Edge: click the install icon in the address bar. Safari: File menu → "Add to Dock"',
            "Launch it anytime from Launchpad or the Dock",
          ]}
        />
      </div>

      <p className="text-xs text-ink-soft text-center">
        This installs a Progressive Web App — the same app you&apos;re using right now, just with its own icon and window,
        and it works offline for things you&apos;ve already loaded.
      </p>
    </div>
  );
}

function PlatformCard({ title, steps }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3">{title}</h2>
      <ol className="flex flex-col gap-2 text-sm text-ink-soft list-decimal list-inside">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
    </div>
  );
}
