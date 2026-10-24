import { useEffect, useState } from "react";
import FileUpload from "@/components/FileUpload";
import { api } from "@/lib/api";
import { categoryLabel, formatPriceRange, groupByCategory } from "@/lib/designs";

const STATUS_CHIP = {
  pending: { label: "In review", className: "text-gold" },
  approved: { label: "Approved ✓", className: "text-leaf" },
  rejected: { label: "Not approved", className: "text-red-700" },
};

/** "Designs I offer" on the artist's profile: pick catalog designs, upload
 * a photo of your own work for each, and track the admin review. Only
 * approved designs show on the design pages and can be booked. */
export default function ArtistDesignsManager() {
  const [catalog, setCatalog] = useState([]);
  const [mine, setMine] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [showCatalog, setShowCatalog] = useState(false);
  const [catalogConsent, setCatalogConsent] = useState(false);

  function load() {
    api.get("/designs").then(setCatalog).catch(() => {});
    api
      .get("/artists/me/designs")
      .then(setMine)
      .catch((e) => setError(e.message));
  }
  useEffect(load, []);

  const offeredIds = new Set(mine.map((m) => m.design.id));
  const notYetOffered = catalog.filter((d) => !offeredIds.has(d.id));

  async function upload(designId, file) {
    setBusyId(designId);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("catalog_consent", catalogConsent ? "true" : "false");
      await api.uploadForm(`/artists/me/designs/${designId}`, form);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(designId) {
    if (!window.confirm("Stop offering this design? Customers won't be able to book you for it.")) return;
    setBusyId(designId);
    try {
      await api.del(`/artists/me/designs/${designId}`);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div>
        <h2 className="font-semibold mb-1">Designs I Offer</h2>
        <p className="text-sm text-ink-soft">
          Pick designs from our catalog and upload a photo of <b>your own</b> work of each one. Our team checks every
          photo — once approved, customers see it on that design&apos;s page and can book you for it.
        </p>
      </div>
      <label className="flex gap-2 items-start text-sm">
        <input type="checkbox" className="mt-1" checked={catalogConsent} onChange={(e) => setCatalogConsent(e.target.checked)} />
        <span>
          AryaVeda may use photos I upload as the main catalog photo of the design.
          <span className="block text-xs text-ink-soft">Optional — applies to the photos you upload while this is ticked.</span>
        </span>
      </label>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {mine.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-3">
          {mine.map((m) => {
            const chip = STATUS_CHIP[m.status] || { label: m.status, className: "" };
            return (
              <div key={m.id} className="border border-line rounded-xl overflow-hidden flex flex-col">
                <div className="grid grid-cols-2 gap-px bg-line">
                  <img src={m.proof_image_url} alt="Your photo" className="w-full aspect-square object-cover bg-ivory" />
                  {m.design.image_url ? (
                    <img src={m.design.image_url} alt="Catalog design" className="w-full aspect-square object-cover bg-ivory" />
                  ) : (
                    <div className="bg-ivory" />
                  )}
                </div>
                <div className="p-3 flex flex-col gap-1 text-sm">
                  <div className="flex justify-between gap-2 items-start">
                    <b className="leading-snug">{m.design.name}</b>
                    <span className={`chip text-[11px] whitespace-nowrap ${chip.className}`}>{chip.label}</span>
                  </div>
                  <span className="text-xs text-ink-soft">
                    {categoryLabel(m.design.category)} · {formatPriceRange(m.design.price_min, m.design.price_max)}
                  </span>
                  {m.design.image_url === m.proof_image_url && <span className="text-xs text-leaf">★ Used as the catalog photo</span>}
                  {m.status === "rejected" && m.rejection_reason && (
                    <p className="text-xs text-red-700">Reason: {m.rejection_reason} — upload a new photo to try again.</p>
                  )}
                  <div className="flex gap-4 items-center mt-1 text-xs">
                    <label className={`text-maroon-soft underline cursor-pointer ${busyId === m.design.id ? "opacity-50 pointer-events-none" : ""}`}>
                      {busyId === m.design.id ? "Uploading…" : "Replace photo"}
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files[0];
                          e.target.value = "";
                          if (file) upload(m.design.id, file);
                        }}
                      />
                    </label>
                    <button type="button" className="text-red-700 underline" onClick={() => remove(m.design.id)} disabled={busyId === m.design.id}>
                      Stop offering
                    </button>
                  </div>
                  <p className="text-[11px] text-ink-soft">A new photo goes back for review before customers see it.</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {notYetOffered.length > 0 && (
        <div className="flex flex-col gap-3">
          <button type="button" className="btn-secondary text-sm self-start" onClick={() => setShowCatalog((v) => !v)}>
            {showCatalog ? "Hide catalog" : `Add designs (${notYetOffered.length} available)`}
          </button>
          {showCatalog &&
            groupByCategory(notYetOffered).map(([cat, designs]) => (
              <div key={cat} className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">{categoryLabel(cat)}</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {designs.map((d) => (
                    <div key={d.id} className="border border-line rounded-xl overflow-hidden flex flex-col">
                      {d.image_url ? (
                        <img src={d.image_url} alt={d.name} className="w-full aspect-square object-cover" />
                      ) : (
                        <div className="w-full aspect-square bg-ivory" />
                      )}
                      <div className="p-2 flex flex-col gap-2 text-xs">
                        <span>
                          <b>{d.name}</b>
                          <br />
                          {formatPriceRange(d.price_min, d.price_max)}
                        </span>
                        <FileUpload
                          onFile={(f) => upload(d.id, f)}
                          busy={busyId === d.id}
                          label="Upload my photo"
                          hint="A photo of mehndi you did in this design"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>
      )}

      {catalog.length === 0 && <p className="text-sm text-ink-soft">The design catalog is empty right now — check back soon.</p>}
    </div>
  );
}
