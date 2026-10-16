import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/useLanguage";
import SectionDivider from "@/components/SectionDivider";

export default function Home() {
  const { t } = useLanguage();
  const [hero, setHero] = useState(null);
  const [story, setStory] = useState(null);
  const [packages, setPackages] = useState([]);

  useEffect(() => {
    api.get("/cms/home.hero", null).then((r) => setHero(r.content)).catch(() => {});
    api.get("/cms/brand.story", null).then((r) => setStory(r.content)).catch(() => {});
    api.get("/packages").then(setPackages).catch(() => {});
  }, []);

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

      <section>
        <h2 className="text-xl mb-4">{t("home_packages_heading")}</h2>
        <PackageGrid packages={packages.filter((p) => p.package_type !== "feet")} t={t} />
      </section>

      <section>
        <h2 className="text-xl mb-1">{t("home_feet_heading")}</h2>
        <p className="text-sm text-ink-soft mb-4">{t("home_feet_sub")}</p>
        <PackageGrid packages={packages.filter((p) => p.package_type === "feet")} t={t} />
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
