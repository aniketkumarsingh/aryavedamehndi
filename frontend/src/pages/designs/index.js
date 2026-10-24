import { useEffect, useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";
import DesignCard from "@/components/DesignCard";
import { api } from "@/lib/api";
import { CATEGORIES, COVERAGES, OCCASIONS, STYLES, categoryLabel, filterDesigns, groupByCategory, optionsPresent } from "@/lib/designs";
import { fetchBackend } from "@/lib/serverApi";

/** Server-rendered (ISR) so the catalog and its prices are crawlable;
 * rebuilt when an admin edits a design (see pages/api/revalidate.js). */
export async function getStaticProps() {
  const designs = await fetchBackend("/designs").catch(() => undefined);
  return {
    props: { initialDesigns: designs ?? null },
    revalidate: designs !== undefined ? 300 : 30,
  };
}

export default function DesignsGallery({ initialDesigns }) {
  const router = useRouter();
  const [designs, setDesigns] = useState(initialDesigns || []);
  const param = (key) => (typeof router.query[key] === "string" ? router.query[key] : "all");
  const category = param("category");
  const filters = { style: param("style"), coverage: param("coverage"), occasion: param("occasion") };
  const filtering = Object.values(filters).some((v) => v !== "all");

  useEffect(() => {
    if (initialDesigns) return; // backend was unreachable at build time
    api.get("/designs").then(setDesigns).catch(() => {});
  }, [initialDesigns]);

  const available = CATEGORIES.filter((c) => designs.some((d) => d.category === c.key));
  const shown = filterDesigns(designs, { category, ...filters });
  const filterSelects = [
    { key: "style", label: "Style", options: optionsPresent(designs, STYLES, "style") },
    { key: "coverage", label: "Coverage", options: optionsPresent(designs, COVERAGES, "coverage") },
    { key: "occasion", label: "Occasion & festival", options: optionsPresent(designs, OCCASIONS, "occasions") },
  ].filter((f) => f.options.length > 1);

  function setQuery(changes) {
    const query = { ...router.query, ...changes };
    for (const key of Object.keys(query)) if (query[key] === "all") delete query[key];
    router.replace({ pathname: "/designs", query }, undefined, { shallow: true, scroll: false });
  }
  const selectCategory = (key) => setQuery({ category: key });

  return (
    <div className="flex flex-col gap-6">
      <Head>
        <title>Mehndi Designs & Prices — AryaVeda Mehndi</title>
        <meta
          name="description"
          content="Browse bridal, party & festive, simple, feet and kids mehndi designs with prices - by style, coverage and occasion - and book a verified artist who has done the exact design."
        />
      </Head>

      <div className="flex flex-col gap-1">
        <h1 className="text-2xl">Mehndi Designs &amp; Prices</h1>
        <p className="text-sm text-ink-soft max-w-2xl">
          Pick a design to see its price and the artists near you who&apos;ve done it — each with a photo of their own work,
          checked by our team.
        </p>
      </div>

      {available.length > 1 && (
        <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Design category">
          {[{ key: "all", label: "All" }, ...available].map((c) => (
            <button
              key={c.key}
              type="button"
              role="tab"
              aria-selected={category === c.key}
              onClick={() => selectCategory(c.key)}
              className={category === c.key ? "btn-primary text-sm" : "btn-secondary text-sm"}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {filterSelects.length > 0 && (
        <div className="flex gap-3 flex-wrap items-end">
          {filterSelects.map((f) => (
            <label key={f.key} className="flex flex-col gap-1 text-xs text-ink-soft">
              {f.label}
              <select className="input w-44" value={filters[f.key]} onChange={(e) => setQuery({ [f.key]: e.target.value })}>
                <option value="all">Any {f.label.toLowerCase()}</option>
                {f.options.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {filtering && (
            <button type="button" className="text-sm text-maroon-soft underline pb-2" onClick={() => setQuery({ style: "all", coverage: "all", occasion: "all" })}>
              Clear filters
            </button>
          )}
        </div>
      )}

      {shown.length === 0 ? (
        <p className="card p-6 text-sm text-ink-soft">
          {designs.length === 0
            ? "Our design catalog is coming soon."
            : filtering
              ? "No designs match these filters - try another style or occasion."
              : `No ${categoryLabel(category).toLowerCase()} designs yet.`}
        </p>
      ) : (
        groupByCategory(shown).map(([cat, items]) => (
          <section key={cat} className="flex flex-col gap-3">
            {category === "all" && <h2 className="text-xl">{categoryLabel(cat)}</h2>}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {items.map((d) => (
                <DesignCard
                  key={d.id}
                  design={d}
                  href={`/designs/${d.id}`}
                  footer={
                    <p className="text-xs text-ink-soft">
                      {d.artist_count > 0 ? `${d.artist_count} verified artist${d.artist_count > 1 ? "s" : ""}` : "No artists yet"}
                    </p>
                  }
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
