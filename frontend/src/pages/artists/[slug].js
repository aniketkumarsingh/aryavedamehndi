import Head from "next/head";
import Link from "next/link";
import SocialMeta, { SITE_URL, absoluteUrl } from "@/components/SocialMeta";
import Stars from "@/components/Stars";
import { formatPriceRange } from "@/lib/designs";
import { fetchBackend } from "@/lib/serverApi";

/** An artist's public portfolio, server-rendered (ISR) for search and for
 * sharing on WhatsApp/Instagram. Only verified artists have one. */
export async function getStaticPaths() {
  return { paths: [], fallback: "blocking" };
}

export async function getStaticProps({ params }) {
  let artist;
  try {
    artist = await fetchBackend(`/artists/by-slug/${encodeURIComponent(params.slug)}`);
  } catch {
    return { props: { artist: null }, revalidate: 30 };
  }
  if (!artist) return { notFound: true, revalidate: 120 };
  return { props: { artist }, revalidate: 600 };
}

function jsonLd(artist) {
  const data = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: `${artist.name} — Mehndi Artist`,
    description: artist.bio || undefined,
    image: artist.profile_photo_url ? absoluteUrl(artist.profile_photo_url) : undefined,
    url: `${SITE_URL}/artists/${artist.slug}`,
    address: artist.city ? { "@type": "PostalAddress", addressLocality: artist.city, addressCountry: "IN" } : undefined,
  };
  if (artist.rating_count > 0) {
    data.aggregateRating = { "@type": "AggregateRating", ratingValue: artist.rating_avg, reviewCount: artist.rating_count };
  }
  return data;
}

export default function ArtistPortfolio({ artist }) {
  if (!artist) return <p className="text-ink-soft">This page couldn&apos;t be loaded right now. Please try again shortly.</p>;
  const title = `${artist.name}${artist.city ? `, Mehndi Artist in ${artist.city}` : " — Mehndi Artist"}`;
  const description = artist.bio || `Book ${artist.name} for bridal, festival and party mehndi at home through AryaVeda Mehndi.`;
  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      <Head>
        <title>{`${title} | AryaVeda Mehndi`}</title>
        <meta key="description" name="description" content={description.slice(0, 160)} />
      </Head>
      <SocialMeta title={title} description={description} image={artist.profile_photo_url} path={`/artists/${artist.slug}`} jsonLd={jsonLd(artist)} />

      <div className="card p-5 flex flex-col sm:flex-row gap-5 items-start">
        <img src={artist.profile_photo_url || "/logo/mark.svg"} alt={artist.name} className="h-28 w-28 rounded-full object-cover border border-line bg-ivory" />
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl leading-tight">{artist.name}</h1>
          <p className="text-sm text-ink-soft">
            Verified mehndi artist{artist.city && ` · ${artist.city}`}
            {artist.completed_bookings > 0 && ` · ${artist.completed_bookings} bookings completed`}
          </p>
          {artist.rating_count > 0 && <Stars value={artist.rating_avg} count={artist.rating_count} />}
          {artist.bio && <p className="text-sm whitespace-pre-line">{artist.bio}</p>}
          <Link href="/discover" className="btn-primary self-start text-sm">Book a mehndi artist</Link>
        </div>
      </div>

      {artist.designs.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl">Designs {artist.name.split(" ")[0]} offers</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {artist.designs.map((d) => (
              <Link key={d.design_id} href={`/designs/${d.design_id}`} className="card overflow-hidden hover:border-gold">
                <img src={d.proof_image_url} alt={d.name} className="w-full aspect-square object-cover bg-ivory" loading="lazy" />
                <div className="p-2 text-sm">
                  <p className="font-semibold leading-snug">{d.name}</p>
                  <p className="text-xs text-ink-soft">{formatPriceRange(d.price_min, d.price_max)}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {artist.portfolio_urls.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl">Portfolio</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {artist.portfolio_urls.map((url) => (
              <img key={url} src={url} alt={`Mehndi by ${artist.name}`} className="w-full aspect-square object-cover rounded-xl border border-line" loading="lazy" />
            ))}
          </div>
        </section>
      )}

      {artist.reviews.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl">What customers say</h2>
          {artist.reviews.map((r, i) => (
            <article key={i} className="card p-4 text-sm flex flex-col gap-1">
              <div className="flex justify-between gap-2 flex-wrap">
                <Stars value={r.rating} />
                <span className="text-xs text-ink-soft">{r.author} · {new Date(r.created_at).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</span>
              </div>
              {r.comment && <p className="text-ink-soft">{r.comment}</p>}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
