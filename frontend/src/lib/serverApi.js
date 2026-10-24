/** Server-side calls to the FastAPI backend (getStaticProps, API routes).
 * The browser goes through the /api rewrite in next.config.js; on the
 * server we call the backend directly. API_BASE_INTERNAL lets production
 * use a private network address instead of the public one. */
export const SERVER_API_BASE = process.env.API_BASE_INTERNAL || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function fetchBackend(path, init = {}) {
  const res = await fetch(`${SERVER_API_BASE}${path}`, { ...init, signal: AbortSignal.timeout(5000) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}
