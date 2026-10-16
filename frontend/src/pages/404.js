import Link from "next/link";

export default function Custom404() {
  return (
    <div className="max-w-md mx-auto text-center flex flex-col items-center gap-4 py-10">
      <img src="/logo/mark.svg" alt="" className="h-20 w-20 opacity-80" />
      <h1 className="text-2xl">Page Not Found</h1>
      <p className="text-sm text-ink-soft">
        This page seems to have wandered off, like a mehndi cone without a cap. Let&apos;s get you back on track.
      </p>
      <div className="flex gap-3">
        <Link href="/" className="btn-primary text-sm">
          Go Home
        </Link>
        <Link href="/discover" className="btn-secondary text-sm">
          Find an Artist
        </Link>
      </div>
    </div>
  );
}
