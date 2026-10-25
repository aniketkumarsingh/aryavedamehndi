import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import DesignCard from "@/components/DesignCard";
import { categoryLabel, groupByCategory } from "@/lib/designs";
import { fetchBackend } from "@/lib/serverApi";
import { useLanguage } from "@/lib/useLanguage";
import SectionDivider from "@/components/SectionDivider";

/** Rendered on the server (ISR) so search engines get the CMS copy and
 * packages in the HTML - organic reach is a Blueprint goal. The page is
 * rebuilt at most every REVALIDATE_SECONDS, and immediately when an admin
 * saves CMS content (see pages/api/revalidate.js). */
const REVALIDATE_SECONDS = 300;

export async function getStaticProps() {
  const results = await Promise.all(
    ["/cms/home.hero", "/cms/brand.story", "/packages", "/designs"].map((path) => fetchBackend(path).catch(() => undefined))
  );
  const [heroRow, storyRow, packages, designs] = results;
  return {
    props: {
      initialHero: heroRow?.content ?? null,
      initialStory: storyRow?.content ?? null,
      initialPackages: packages ?? null,
      initialDesigns: designs ?? null,
      // Backend unreachable at build time - the browser fetches instead.
      serverFetched: packages !== undefined,
    },
    revalidate: packages !== undefined ? REVALIDATE_SECONDS : 30,
  };
}

export default function Home({
  initialHero = null,
  initialStory = null,
  initialPackages = null,
  initialDesigns = null,
  serverFetched = false,
}) {
  const { t } = useLanguage();
  const [hero, setHero] = useState(initialHero);
  const [story, setStory] = useState(initialStory);
  const [packages, setPackages] = useState(initialPackages || []);
  const [designs, setDesigns] = useState(initialDesigns || []);

  useEffect(() => {
    if (serverFetched) return;
    api.get("/cms/home.hero", null).then((r) => setHero(r.content)).catch(() => {});
    api.get("/cms/brand.story", null).then((r) => setStory(r.content)).catch(() => {});
    api.get("/packages").then(setPackages).catch(() => {});
    api.get("/designs").then(setDesigns).catch(() => {});
  }, [serverFetched]);

  return (
    <div className="flex flex-col gap-14">
      <Head>
        <title>AryaVeda Mehndi — Ayurvedic Mehndi, Booked Safely</title>
        <script type="application/ld+json" dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            name: "AryaVeda Mehndi",
            description: "Ayurvedic, organic mehndi artists booked safely near you.",
            areaServed: "IN",
          }),
        }} />
      </Head>
      <section className="invitation-frame text-center flex flex-col items-center gap-5 px-6 py-12 sm:px-14 sm:py-16 mx-2 sm:mx-6 overflow-hidden">
        <span className="corner-tl" aria-hidden="true" />
        <span className="corner-tr" aria-hidden="true" />
        <span className="corner-bl" aria-hidden="true" />
        <span className="corner-br" aria-hidden="true" />
        <img
          src="/patterns/mandala.svg"
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 w-[520px] max-w-none -translate-x-1/2 -translate-y-1/2 opacity-[0.16]"
        />
        <span className="chip relative">{t("home_badge")}</span>
        <h1 className="relative text-3xl sm:text-4xl font-semibold max-w-2xl text-balance">
          {hero?.headline || t("home_hero_headline")}
        </h1>
        <p className="relative text-ink-soft max-w-xl">
          {hero?.subheadline || t("home_hero_sub")}
        </p>
        <Link href="/discover" className="btn-primary relative">
          {hero?.cta_label || t("home_hero_cta")}
        </Link>
      </section>

      {story && (
        <section className="card p-6 max-w-2xl mx-auto text-center">
          <h2 className="text-xl mb-2">{story.title}</h2>
          <p className="text-ink-soft">{story.body}</p>
        </section>
      )}

      <SectionDivider />

      {designs.length > 0 && (
        <section className="flex flex-col gap-4">
          <div className="flex justify-between items-end gap-2 flex-wrap">
            <div>
              <h2 className="text-xl">{t("home_designs_heading")}</h2>
              <p className="text-sm text-ink-soft">{t("home_designs_sub")}</p>
            </div>
            <Link href="/designs" className="btn-secondary text-sm">
              {t("home_designs_cta")}
            </Link>
          </div>
          {groupByCategory(designs).map(([cat, items]) => (
            <div key={cat} className="flex flex-col gap-2">
              <div className="flex justify-between items-baseline">
                <h3 className="font-semibold">{categoryLabel(cat)}</h3>
                {items.length > 4 && (
                  <Link href={`/designs?category=${cat}`} className="text-sm text-maroon-soft underline">
                    All {items.length}
                  </Link>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {items.slice(0, 4).map((d) => (
                  <DesignCard key={d.id} design={d} href={`/designs/${d.id}`} />
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      <section>
        <h2 className="text-xl mb-4">{t("home_packages_heading")}</h2>
        <PackageGrid packages={packages.filter((p) => p.package_type !== "feet")} t={t} />
      </section>

      <section>
        <h2 className="text-xl mb-1">{t("home_feet_heading")}</h2>
        <p className="text-sm text-ink-soft mb-4">{t("home_feet_sub")}</p>
        <PackageGrid packages={packages.filter((p) => p.package_type === "feet")} t={t} />
      </section>

      <section className="maroon-panel px-6 py-10 sm:px-12 grid md:grid-cols-[1fr_auto] gap-6 items-center">
        <img src="/patterns/mandala.svg" alt="" aria-hidden="true" className="pointer-events-none absolute -right-20 -bottom-24 w-96 opacity-[0.2]" />
        <div className="relative flex flex-col gap-2">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-gold-soft/80">{t("home_custom_eyebrow")}</p>
          <h2 className="text-2xl sm:text-3xl font-semibold text-ivory-raised text-balance">{t("home_custom_heading")}</h2>
          <p className="text-gold-soft max-w-xl text-sm sm:text-base">{t("home_custom_sub")}</p>
        </div>
        <div className="relative flex flex-col sm:flex-row md:flex-col gap-3">
          <Link href="/custom-order" className="rounded-[10px] bg-ivory-raised text-maroon font-semibold px-5 py-3 text-center hover:bg-gold-soft transition-colors">
            {t("home_custom_single")}
          </Link>
          <Link href="/custom-order?type=bulk" className="rounded-[10px] ring-1 ring-gold-soft text-ivory-raised font-semibold px-5 py-3 text-center hover:bg-ivory-raised/10 transition-colors">
            {t("home_custom_bulk")}
          </Link>
        </div>
      </section>

      <SectionDivider />

      <section className="grid sm:grid-cols-3 gap-4 text-sm">
        <div className="card p-4">
          <h3 className="font-semibold mb-1">{t("home_feature_gender_title")}</h3>
          <p className="text-ink-soft">{t("home_feature_gender_body")}</p>
        </div>
        <div className="card p-4">
          <h3 className="font-semibold mb-1">{t("home_feature_payment_title")}</h3>
          <p className="text-ink-soft">{t("home_feature_payment_body")}</p>
        </div>
        <div className="card p-4">
          <h3 className="font-semibold mb-1">{t("home_feature_pricing_title")}</h3>
          <p className="text-ink-soft">{t("home_feature_pricing_body")}</p>
        </div>
      </section>
    </div>
  );
}

function PackageGrid({ packages, t }) {
  if (packages.length === 0) {
    return <p className="text-ink-soft text-sm">{t("home_no_packages")}</p>;
  }
  return (
    <div className="grid sm:grid-cols-3 gap-4">
      {packages.map((p) => {
        const images = (p.sample_image_urls || "").split(",").filter(Boolean);
        return (
          <div key={p.id} className="card overflow-hidden">
            {images.length > 0 && (
              <img
                src={images[0]}
                alt={`${p.name} sample design`}
                className="w-full h-40 object-contain bg-ivory border-b border-line"
              />
            )}
            <div className="p-4">
              <span className="chip">{p.package_type}</span>
              <h3 className="text-lg mt-2">{p.name}</h3>
              <p className="text-sm text-ink-soft mt-1">{p.description}</p>
              <p className="text-sm mt-3 font-semibold text-maroon-soft">
                ₹{p.price_min} – ₹{p.price_max} · ~{p.duration_minutes} min
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
