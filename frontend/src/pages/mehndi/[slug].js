import Head from "next/head";
import Link from "next/link";
import SocialMeta, { SITE_URL } from "@/components/SocialMeta";
import Stars from "@/components/Stars";
import { formatPriceRange } from "@/lib/designs";
import { fetchBackend } from "@/lib/serverApi";

/** City / occasion landing pages (e.g. /mehndi/bridal-mehndi-artist-jaipur),
 * written in Admin → Growth and filled with live artists and designs. */
export async function getStaticPaths() {
  return { paths: [], fallback: "blocking" };
}

export async function getStaticProps({ params }) {
  let page;
  try {
    page = await fetchBackend(`/landing-pages/${encodeURIComponent(params.slug)}`);
  } catch {
    return { props: { page: null }, revalidate: 30 };
  }
  if (!page) return { notFound: true, revalidate: 120 };
  return { props: { page }, revalidate: 900 };
}

export default function LandingPage({ page }) {
  if (!page) return <p className="text-ink-soft">This page couldn&apos;t be loaded right now. Please try again shortly.</p>;
  const description = page.meta_description || page.intro?.slice(0, 160) || page.heading;
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: page.heading,
    itemListElement: page.artists.map((a, i) => ({ "@type": "ListItem", position: i + 1, url: `${SITE_URL}/artists/${a.slug}`, name: a.name })),
  };
  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <Head>
        <title>{`${page.title} | AryaVeda Mehndi`}</title>
        <meta key="description" name="description" content={description} />
      </Head>
      <SocialMeta title={page.title} description={description} path={`/mehndi/${page.slug}`} jsonLd={jsonLd} />

      <div className="flex flex-col gap-2">
        <h1 className="text-3xl leading-tight">{page.heading}</h1>
        {page.intro && <p className="text-ink-soft whitespace-pre-line">{page.intro}</p>}
        <Link href="/discover" className="btn-primary self-start">Find an artist near you</Link>
      </div>

      {page.artists.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl">Verified artists{page.city && ` in ${page.city}`}</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {page.artists.map((a) => (
              <Link key={a.slug} href={`/artists/${a.slug}`} className="card p-4 flex gap-3 items-center hover:border-gold">
                <img src={a.profile_photo_url || "/logo/mark.svg"} alt={a.name} className="h-16 w-16 rounded-full object-cover border border-line bg-ivory" loading="lazy" />
                <div className="flex flex-col">
                  <span className="font-semibold">{a.name}</span>
                  {a.city && <span className="text-xs text-ink-soft">{a.city}</span>}
                  {a.rating_count > 0 && <Stars value={a.rating_avg} count={a.rating_count} />}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {page.designs.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl">Popular designs</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {page.designs.map((d) => (
              <Link key={d.id} href={`/designs/${d.id}`} className="card overflow-hidden hover:border-gold">
                <img src={d.image_url || "/logo/mark.svg"} alt={d.name} className="w-full aspect-square object-cover bg-ivory" loading="lazy" />
                <div className="p-2 text-sm">
                  <p className="font-semibold leading-snug">{d.name}</p>
                  <p className="text-xs text-ink-soft">{formatPriceRange(d.price_min, d.price_max)}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
