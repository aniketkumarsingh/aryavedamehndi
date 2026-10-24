import { fetchBackend } from "@/lib/serverApi";

/** On-demand ISR: the admin panel calls this after saving CMS content or a
 * catalog design, so server-rendered pages pick up the change immediately
 * instead of after the revalidate window. Only admins can trigger it - the
 * caller's own access token is checked against the backend. Next.js API
 * routes take precedence over the /api/* rewrite to the backend.
 *
 * Body: { paths?: string[] } - defaults to the home page. Only paths this
 * route knows are server-rendered are accepted. */
const ALLOWED = [/^\/$/, /^\/designs$/, /^\/designs\/[0-9a-f-]{36}$/];

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  const auth = req.headers.authorization || "";
  let me;
  try {
    me = await fetchBackend("/users/me", { headers: { Authorization: auth } });
  } catch {
    me = null;
  }
  if (!me || me.role !== "admin") return res.status(403).json({ detail: "Admins only" });

  const requested = Array.isArray(req.body?.paths) && req.body.paths.length ? req.body.paths : ["/"];
  const paths = [...new Set(requested)].slice(0, 20);
  if (!paths.every((p) => typeof p === "string" && ALLOWED.some((re) => re.test(p)))) {
    return res.status(400).json({ detail: "Unsupported path" });
  }

  const results = await Promise.allSettled(paths.map((p) => res.revalidate(p)));
  // A design page that was never generated yet can't be revalidated - it
  // renders fresh on first visit anyway, so that isn't an error.
  return res.json({ revalidated: paths.filter((_, i) => results[i].status === "fulfilled") });
}
