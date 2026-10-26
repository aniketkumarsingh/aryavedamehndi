import { SITE_URL } from "@/components/SocialMeta";
import { fetchBackend } from "@/lib/serverApi";

// Built on request (cached for an hour) from the live designs and shop
// products, so new ones reach search engines without a redeploy.
const STATIC_PAGES = [
  ["/", "1.0"],
  ["/designs", "0.9"],
  ["/shop", "0.9"],
  ["/discover", "0.9"],
  ["/custom-order", "0.7"],
  ["/download", "0.5"],
  ["/contact", "0.4"],
  ["/legal/terms", "0.3"],
  ["/legal/privacy", "0.3"],
  ["/legal/refunds", "0.3"],
  ["/legal/shipping", "0.3"],
];

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export async function getServerSideProps({ res }) {
  const [designs, products] = await Promise.all([
    fetchBackend("/designs").catch(() => []),
    fetchBackend("/shop/products").catch(() => []),
  ]);
  const urls = [
    ...STATIC_PAGES.map(([path, priority]) => ({ path, priority })),
    ...(designs || []).map((d) => ({ path: `/designs/${d.id}`, priority: "0.8" })),
    ...(products || []).filter((p) => p.slug).map((p) => ({ path: `/shop/${p.slug}`, priority: "0.8" })),
  ];
  const xml =
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    urls.map((u) => `  <url><loc>${escape(SITE_URL + u.path)}</loc><priority>${u.priority}</priority></url>`).join("\n") +
    `\n</urlset>\n`;
  res.setHeader("Content-Type", "application/xml; charset=utf-8");
  res.setHeader("Cache-Control", "public, s-maxage=3600, stale-while-revalidate=86400");
  res.write(xml);
  res.end();
  return { props: {} };
}

export default function Sitemap() {
  return null;
}
