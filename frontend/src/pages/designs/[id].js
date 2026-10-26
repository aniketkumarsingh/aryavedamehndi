import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import DesignGallery from "@/components/DesignGallery";
import SocialMeta from "@/components/SocialMeta";
import { api } from "@/lib/api";
import { categoryLabel, coverageLabel, formatDuration, formatPriceRange, occasionLabel, styleLabel } from "@/lib/designs";
import { fetchBackend } from "@/lib/serverApi";

/** Design info is server-rendered (ISR) for search engines. The artist
 * list depends on where the visitor is, so it's loaded in the browser. */
export async function getStaticPaths() {
  return { paths: [], fallback: "blocking" };
}

export async function getStaticProps({ params }) {
  let design;
  try {
    design = await fetchBackend(`/designs/${params.id}`);
  } catch {
    // Backend unreachable - render a shell and retry soon.
    return { props: { initialDesign: null, id: params.id }, revalidate: 30 };
  }
  if (!design) return { notFound: true, revalidate: 60 };
  return { props: { initialDesign: design, id: params.id }, revalidate: 300 };
}

export default function DesignDetail({ initialDesign, id }) {
  const [design, setDesign] = useState(initialDesign);
  const [artists, setArtists] = useState(null);
  const [locationNote, setLocationNote] = useState("");

  useEffect(() => {
    function load(query) {
      api
        .get(`/designs/${id}`, query)
        .then((d) => {
          setDesign(d);
          setArtists(d.artists);
        })
        .catch(() => setArtists([]));
    }
    if (!navigator.geolocation) {
      setLocationNote("Showing all artists — your browser can't share location.");
      return load();
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => load({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => {
        setLocationNote("Showing all artists. Allow location to see only those who travel to you.");
        load();
      },
      { timeout: 8000 }
    );
  }, [id]);

  if (!design) return <p className="text-ink-soft">Loading design…</p>;

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      <Head>
        <title>{`${design.name} — ${formatPriceRange(design.price_min, design.price_max)} | AryaVeda Mehndi`}</title>
        <meta key="description" name="description" content={design.description || `${categoryLabel(design.category)} mehndi design by verified artists.`} />
      </Head>
      <SocialMeta
        title={`${design.name} — AryaVeda Mehndi`}
        description={design.description || `${categoryLabel(design.category)} mehndi design by verified artists.`}
        image={design.image_url}
        path={`/designs/${id}`}
      />

      <Link href={`/designs?category=${design.category}`} className="text-sm text-maroon-soft underline self-start">
        ← {categoryLabel(design.category)} designs
      </Link>

      <div className="grid md:grid-cols-2 gap-6">
        <DesignGallery design={design} />
        <div className="flex flex-col gap-3">
          <div className="flex gap-2 flex-wrap">
            <span className="chip">{categoryLabel(design.category)}</span>
            {design.style && (
              <Link href={`/designs?style=${design.style}`} className="chip hover:ring-1 hover:ring-gold">
                {styleLabel(design.style)}
              </Link>
            )}
            {design.coverage && <span className="chip">{coverageLabel(design.coverage)}</span>}
          </div>
          <h1 className="text-2xl">{design.name}</h1>
          <p className="text-xl font-semibold text-maroon-soft">{formatPriceRange(design.price_min, design.price_max)}</p>
          <p className="text-sm text-ink-soft">Takes about {formatDuration(design.duration_minutes)}</p>
          {design.description && <p className="text-sm">{design.description}</p>}
          {design.occasions?.length > 0 && (
            <p className="text-sm">
              <span className="text-ink-soft">Good for: </span>
              {design.occasions.map((o, i) => (
                <span key={o}>
                  {i > 0 && ", "}
                  <Link href={`/designs?occasion=${o}`} className="text-maroon-soft underline">
                    {occasionLabel(o)}
                  </Link>
                </span>
              ))}
            </p>
          )}
          <p className="text-xs text-ink-soft border-l-2 border-gold pl-2">
            The final price is agreed with your artist within this range. After the session, the finished mehndi is
            checked against this design photo before you pay.
          </p>
        </div>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl">Artists who&apos;ve done this design</h2>
        <p className="text-xs text-ink-soft">
          Each photo is the artist&apos;s own work of this design, verified by our team.
          {locationNote && ` ${locationNote}`}
        </p>
        {artists === null ? (
          <p className="text-sm text-ink-soft">Finding artists…</p>
        ) : artists.length === 0 ? (
          <p className="card p-5 text-sm text-ink-soft">
            No verified artists offer this design in your area yet.{" "}
            <Link href="/discover" className="text-maroon-soft underline">
              Browse all artists
            </Link>
          </p>
        ) : (
          <div className="grid sm:grid-cols-2 gap-4">
            {artists.map((a) => (
              <div key={a.artist_id} className="card overflow-hidden flex flex-col">
                <div className="grid grid-cols-2 gap-px bg-line">
                  <figure className="bg-ivory">
                    <img src={a.proof_image_url} alt={`${a.name || "Artist"}'s ${design.name}`} className="w-full aspect-square object-cover" />
                    <figcaption className="text-[11px] text-center py-1 text-ink-soft">Their work ✓ verified</figcaption>
                  </figure>
                  <figure className="bg-ivory">
                    {design.image_url ? (
                      <img src={design.image_url} alt="Catalog design" className="w-full aspect-square object-cover" />
                    ) : (
                      <div className="w-full aspect-square" />
                    )}
                    <figcaption className="text-[11px] text-center py-1 text-ink-soft">
                      {design.image_kind === "illustration" ? "Catalog illustration" : "Catalog design"}
                    </figcaption>
                  </figure>
                </div>
                <div className="p-4 flex items-center gap-3">
                  <img
                    src={a.profile_photo_url || "/avatars/preset-1.svg"}
                    alt=""
                    className="h-12 w-12 rounded-full object-cover border-2 border-gold flex-none"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold truncate">{a.name || "Mehndi Artist"}</p>
                    <p className="text-xs text-ink-soft">
                      {a.rating_count > 0 ? `★ ${a.rating_avg} (${a.rating_count})` : "New artist"}
                      {a.distance_km != null && ` · ${a.distance_km} km · ~${a.eta_minutes} min away`}
                    </p>
                  </div>
                  <Link
                    href={`/booking/${a.artist_id}?package_id=${design.package_id}&design_id=${design.id}`}
                    className="btn-primary text-sm whitespace-nowrap"
                  >
                    Book
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
