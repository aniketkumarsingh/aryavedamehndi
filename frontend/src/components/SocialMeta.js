import Head from "next/head";

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://www.aryavedamehndi.com").replace(/\/$/, "");
// Uploaded images are served by the API (/media/...) unless S3 gives full URLs.
const MEDIA_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "");

export function absoluteUrl(url) {
  if (!url) return `${SITE_URL}/icons/icon-512.png`;
  if (/^https?:\/\//.test(url)) return url;
  return url.startsWith("/media/") ? `${MEDIA_BASE}${url}` : `${SITE_URL}${url}`;
}

/** Link-preview tags for WhatsApp, Facebook, Instagram and X shares, plus
 * optional JSON-LD structured data for Google rich results. */
export default function SocialMeta({ title, description, image, path, type = "website", jsonLd }) {
  const url = `${SITE_URL}${path || ""}`;
  return (
    <Head>
      <meta key="og:site_name" property="og:site_name" content="AryaVeda Mehndi" />
      <meta key="og:type" property="og:type" content={type} />
      <meta key="og:title" property="og:title" content={title} />
      {description && <meta key="og:description" property="og:description" content={description} />}
      <meta key="og:image" property="og:image" content={absoluteUrl(image)} />
      <meta key="og:url" property="og:url" content={url} />
      <meta key="twitter:card" name="twitter:card" content="summary_large_image" />
      <link key="canonical" rel="canonical" href={url} />
      {jsonLd && <script key="jsonld" type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />}
    </Head>
  );
}
