import Head from "next/head";

/** Served by the service worker (next-pwa picks this file up as the
 * document fallback) when a page is opened offline that was never loaded
 * before. Precached at install, so it must not depend on API data. */
export default function Offline() {
  return (
    <div className="max-w-md mx-auto flex flex-col items-center gap-4 text-center py-12">
      <Head>
        <title>You&apos;re offline — AryaVeda Mehndi</title>
      </Head>
      <img src="/logo/mark.svg" alt="" className="h-16 w-16" />
      <h1 className="text-2xl">You&apos;re offline</h1>
      <p className="text-sm text-ink-soft">
        This page hasn&apos;t been opened on this device before, so it isn&apos;t saved for offline use. Pages you&apos;ve
        already visited still open. Bookings, chat and payments need a connection.
      </p>
      <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
        Try again
      </button>
    </div>
  );
}
