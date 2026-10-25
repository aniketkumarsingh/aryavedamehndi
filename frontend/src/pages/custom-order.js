import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import FileUpload from "@/components/FileUpload";
import { Icon, OrnateHero, QuantityStepper, Receipt, StepHeading } from "@/components/OrderParts";
import PricePromise from "@/components/PricePromise";
import SectionDivider from "@/components/SectionDivider";
import { api } from "@/lib/api";
import { categoryLabel, formatDuration, formatPriceRange } from "@/lib/designs";
import { BULK_OCCASIONS, bulkOccasionLabel, estimateSummary } from "@/lib/pricing";
import { useAuth } from "@/lib/useAuth";

const MODES = [
  {
    key: "single",
    icon: "hand",
    title: "Just me — my own design",
    body: "Saw a design you love? Upload it and book a verified artist near you.",
    points: ["Any photo or screenshot", "Priced at the package's usual range", "Finished mehndi checked against it"],
  },
  {
    key: "bulk",
    icon: "people",
    title: "Event / bulk order",
    body: "Mehndi for the bride, family and every guest at your function.",
    points: ["Mix bridal, simple & kids' groups", "Same per-person price as booking alone", "We line up the artists for you"],
  },
];

// Shown as quick picks; every occasion stays in the "More" dropdown.
const QUICK_OCCASIONS = ["mehndi-ceremony", "wedding", "sangeet", "haldi", "karwa-chauth", "teej", "eid", "diwali"];

export default function CustomOrder() {
  const router = useRouter();
  const { user, ready } = useAuth();
  const [packages, setPackages] = useState([]);
  const mode = router.query.type === "bulk" ? "bulk" : "single";

  useEffect(() => {
    api.get("/packages").then(setPackages).catch(() => {});
  }, []);

  function setMode(key) {
    router.replace({ pathname: "/custom-order", query: key === "bulk" ? { type: "bulk" } : {} }, undefined, { shallow: true });
  }

  return (
    <div className="flex flex-col gap-8 max-w-5xl mx-auto">
      <Head>
        <title>Custom & Event Mehndi Orders | AryaVeda Mehndi</title>
        <meta name="description" content="Book mehndi in your own design, or for every guest at your mehndi ceremony, sangeet or festival — at the same transparent per-person prices." />
      </Head>

      <OrnateHero eyebrow="Custom & Event Orders" title="Your design. Your celebration.">
        Bring the design you&apos;ve been saving, or get mehndi for everyone at your function — at exactly the prices you see
        everywhere else on AryaVeda.
      </OrnateHero>

      <div className="grid sm:grid-cols-2 gap-4" role="tablist" aria-label="Kind of order">
        {MODES.map((m) => (
          <button key={m.key} role="tab" aria-selected={mode === m.key} onClick={() => setMode(m.key)} className="option-card p-5 flex gap-4">
            <span className={`w-14 h-14 rounded-2xl flex items-center justify-center flex-none ${mode === m.key ? "bg-maroon text-gold-soft" : "bg-gold-soft text-gold"}`}>
              <Icon name={m.icon} className="w-7 h-7" />
            </span>
            <span className="flex flex-col gap-1">
              <span className="font-display text-lg font-semibold text-maroon leading-tight">{m.title}</span>
              <span className="text-sm text-ink-soft">{m.body}</span>
              <span className="flex flex-col gap-0.5 mt-1">
                {m.points.map((p) => (
                  <span key={p} className="text-xs flex gap-1.5">
                    <span className="text-gold">✦</span>
                    {p}
                  </span>
                ))}
              </span>
            </span>
          </button>
        ))}
      </div>

      {ready && user?.role !== "consumer" ? (
        <div className="card p-8 text-center flex flex-col items-center gap-3">
          <span className="w-12 h-12 rounded-full bg-gold-soft text-gold flex items-center justify-center">
            <Icon name="sparkle" />
          </span>
          {user ? (
            <p className="text-sm">Custom orders are placed from a customer account.</p>
          ) : (
            <>
              <p className="font-display text-lg text-maroon">Log in to place your order</p>
              <p className="text-sm text-ink-soft">It only takes your phone number — no password needed.</p>
              <Link href="/login" className="btn-primary">
                Log in to continue
              </Link>
            </>
          )}
        </div>
      ) : mode === "single" ? (
        <SingleOrder packages={packages} />
      ) : (
        <BulkOrder packages={packages} />
      )}

      <SectionDivider />
      <PricePromise />
    </div>
  );
}

function useEstimate(lines) {
  const [estimate, setEstimate] = useState(null);
  const key = JSON.stringify(lines);
  useEffect(() => {
    if (lines.length === 0) {
      setEstimate(null);
      return;
    }
    const t = setTimeout(() => {
      api.post("/pricing/estimate", { lines }).then(setEstimate).catch(() => setEstimate(null));
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return estimate;
}

function EmptyReceipt({ text }) {
  return (
    <div className="rounded-[14px] border-2 border-dashed border-line p-6 text-center text-sm text-ink-soft flex flex-col items-center gap-2">
      <Icon name="receipt" className="w-8 h-8 text-gold" />
      {text}
    </div>
  );
}

// ------------------------------------------------------------ single order --

function SingleOrder({ packages }) {
  const router = useRouter();
  const [imageUrl, setImageUrl] = useState("");
  const [packageId, setPackageId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const estimate = useEstimate(packageId ? [{ package_id: packageId, quantity: 1 }] : []);
  const s = estimateSummary(estimate);
  const pkg = packages.find((p) => p.id === packageId);

  async function upload(file) {
    setBusy(true);
    setError("");
    try {
      const { url } = await api.upload("/bookings/reference-image", file);
      setImageUrl(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function findArtist() {
    router.push({ pathname: "/discover", query: { package_id: packageId, reference: imageUrl } });
  }

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start fade-up">
      <div className="card p-6 sm:p-8 flex flex-col gap-8">
        <section className="flex flex-col gap-3">
          <StepHeading n={1} title="Upload the design you want" hint="A photo or screenshot of any mehndi design — your artist uses it as the brief." />
          {imageUrl ? (
            <div className="relative self-start">
              <img src={imageUrl} alt="Your design" className="w-56 h-56 object-cover rounded-2xl border-4 border-ivory-raised ring-1 ring-gold shadow-lg" />
              <span className="absolute -top-2 -left-2 chip bg-maroon text-ivory-raised shadow">Your design</span>
              <div className="mt-2 w-56">
                <FileUpload onFile={upload} busy={busy} label="Replace design" />
              </div>
            </div>
          ) : (
            <FileUpload onFile={upload} busy={busy} label="Upload your design" hint="JPG, PNG or WEBP — we'll check the finished mehndi against it before you pay." />
          )}
        </section>

        <section className="flex flex-col gap-3">
          <StepHeading n={2} title="Pick the closest kind of mehndi" hint="This sets the price range — the same range anyone booking this package pays." />
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {packages.map((p) => {
              const sample = (p.sample_image_urls || "").split(",").find(Boolean);
              return (
                <button key={p.id} type="button" aria-pressed={packageId === p.id} onClick={() => setPackageId(p.id)} className="option-card overflow-hidden flex flex-col">
                  <span className="relative block h-24 bg-ivory overflow-hidden">
                    {sample ? (
                      <img src={sample} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <img src="/patterns/mandala.svg" alt="" className="absolute inset-0 m-auto w-28 opacity-30" />
                    )}
                    {packageId === p.id && <span className="absolute top-2 right-2 w-6 h-6 rounded-full bg-maroon text-ivory-raised text-xs flex items-center justify-center">✓</span>}
                  </span>
                  <span className="p-3 flex flex-col gap-0.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gold">{categoryLabel(p.package_type)}</span>
                    <span className="font-semibold text-sm leading-tight">{p.name}</span>
                    <span className="text-xs font-semibold text-maroon-soft">{formatPriceRange(p.price_min, p.price_max)}</span>
                    <span className="text-[11px] text-ink-soft">~{formatDuration(p.duration_minutes)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <StepHeading n={3} title="Choose an artist near you" hint="Verified, gender-matched artists — sorted by rating." />
          {error && <p className="text-sm text-red-700">{error}</p>}
          <button className="btn-primary self-start px-6 py-3 text-base" disabled={!imageUrl || !packageId} onClick={findArtist}>
            Find my artist →
          </button>
          {(!imageUrl || !packageId) && <p className="text-xs text-ink-soft">Upload your design and pick a package to continue.</p>}
        </section>
      </div>

      <aside className="lg:sticky lg:top-24 flex flex-col gap-4">
        {s ? (
          <Receipt
            title="Your estimate"
            subtitle={pkg ? `${categoryLabel(pkg.package_type)} · ${pkg.name}` : undefined}
            rows={[
              ["Mehndi", s.subtotal],
              ["Platform fee", s.fee],
            ]}
            total={["Total", s.total]}
            footnotes={[
              "You agree the final price with your artist — never above this range.",
              s.deposit && `${s.deposit} deposit secures your slot, refundable until your artist heads out.`,
            ]}
          />
        ) : (
          <EmptyReceipt text="Pick a package to see exactly what your design will cost." />
        )}
      </aside>
    </div>
  );
}

// -------------------------------------------------------------- bulk order --

const newLine = () => ({ key: Math.random().toString(36).slice(2), package_id: "", design_id: "", quantity: 1, reference_image_url: "", note: "" });

function BulkOrder({ packages }) {
  const router = useRouter();
  const [designs, setDesigns] = useState([]);
  const [occasion, setOccasion] = useState("mehndi-ceremony");
  const [eventAt, setEventAt] = useState("");
  const [address, setAddress] = useState("");
  const [genderPref, setGenderPref] = useState("same");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([newLine()]);
  const [uploadingKey, setUploadingKey] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/designs").then(setDesigns).catch(() => {});
  }, []);

  const filled = lines.filter((l) => l.package_id && Number(l.quantity) >= 1);
  const readyLines = filled.map((l) => ({ package_id: l.package_id, design_id: l.design_id || null, quantity: Number(l.quantity) }));
  const estimate = useEstimate(readyLines);
  const s = estimateSummary(estimate);

  function lineLabel(l) {
    const design = designs.find((d) => d.id === l.design_id);
    const pkg = packages.find((p) => p.id === l.package_id);
    return design?.name || pkg?.name || "Mehndi";
  }

  function updateLine(key, changes) {
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...changes } : l)));
  }

  async function uploadFor(key, file) {
    setUploadingKey(key);
    setError("");
    try {
      const { url } = await api.upload("/bookings/reference-image", file);
      updateLine(key, { reference_image_url: url });
    } catch (e) {
      setError(e.message);
    } finally {
      setUploadingKey(null);
    }
  }

  async function submit(e) {
    e.preventDefault();
    if (filled.length !== lines.length) {
      setError("Pick a kind of mehndi for every group, or remove the empty one.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      // Optional - helps us pick artists near the venue.
      const coords = await new Promise((resolve) => {
        if (!navigator.geolocation) return resolve({});
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve({ location_lat: pos.coords.latitude, location_lng: pos.coords.longitude }),
          () => resolve({}),
          { timeout: 4000 }
        );
      });
      const order = await api.post("/bulk-orders", {
        occasion,
        event_at: new Date(eventAt).toISOString(),
        address_text: address,
        gender_preference: genderPref,
        notes: notes || null,
        ...coords,
        lines: lines.map((l) => ({
          package_id: l.package_id,
          design_id: l.design_id || null,
          quantity: Number(l.quantity),
          reference_image_url: l.design_id ? null : l.reference_image_url || null,
          note: l.note || null,
        })),
      });
      router.push(`/bulk-orders/${order.id}`);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start fade-up">
      <div className="card p-6 sm:p-8 flex flex-col gap-8">
        <section className="flex flex-col gap-4">
          <StepHeading n={1} title="The occasion" hint="Tell us what you're celebrating, when and where." />
          <div className="flex flex-wrap gap-2">
            {QUICK_OCCASIONS.map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={occasion === key}
                onClick={() => setOccasion(key)}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition-colors ${
                  occasion === key ? "bg-maroon border-maroon text-ivory-raised" : "border-line bg-ivory-raised text-ink-soft hover:border-gold"
                }`}
              >
                {bulkOccasionLabel(key)}
              </button>
            ))}
            <select
              className={`rounded-full border px-3 py-1.5 text-sm font-semibold bg-ivory-raised ${QUICK_OCCASIONS.includes(occasion) ? "border-line text-ink-soft" : "border-maroon text-maroon"}`}
              value={QUICK_OCCASIONS.includes(occasion) ? "" : occasion}
              onChange={(e) => e.target.value && setOccasion(e.target.value)}
              aria-label="More occasions"
            >
              <option value="">More occasions…</option>
              {BULK_OCCASIONS.filter((o) => !QUICK_OCCASIONS.includes(o.key)).map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-sm font-semibold flex items-center gap-1.5">
                <Icon name="calendar" className="w-4 h-4 text-gold" /> Date &amp; start time
              </span>
              <input className="input" type="datetime-local" value={eventAt} onChange={(e) => setEventAt(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-sm font-semibold flex items-center gap-1.5">
                <Icon name="pin" className="w-4 h-4 text-gold" /> Venue address
              </span>
              <input className="input" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Where is the function?" required minLength={5} />
            </label>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <StepHeading n={2} title="Who needs mehndi?" hint="Add a group for each kind — e.g. 1 bride, 20 guests, 6 kids. Each person is priced exactly as if they booked alone." />

          {lines.map((line, i) => {
            const pkg = packages.find((p) => p.id === line.package_id);
            const pkgDesigns = designs.filter((d) => d.package_id === line.package_id);
            const design = pkgDesigns.find((d) => d.id === line.design_id);
            const band = design || pkg;
            const preview = design?.image_url || line.reference_image_url;
            return (
              <div key={line.key} className="rounded-2xl border border-line border-l-4 border-l-gold bg-ivory/60 p-4 sm:p-5 flex flex-col gap-3 fade-up">
                <div className="flex justify-between items-center gap-2">
                  <p className="font-display font-semibold text-maroon flex items-center gap-2">
                    <Icon name="people" className="w-5 h-5 text-gold" /> Group {i + 1}
                    {pkg && <span className="chip">{categoryLabel(pkg.package_type)}</span>}
                  </p>
                  {lines.length > 1 && (
                    <button type="button" className="text-xs text-red-700 hover:underline" onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}>
                      Remove
                    </button>
                  )}
                </div>

                <div className="flex gap-4 items-start">
                  {preview && <img src={preview} alt="" className="w-20 h-20 rounded-xl object-cover border-2 border-ivory-raised ring-1 ring-gold flex-none" />}
                  <div className="flex-1 flex flex-col gap-3 min-w-0">
                    <div className="flex flex-wrap gap-3 items-center">
                      <select className="input flex-1 min-w-[12rem]" value={line.package_id} onChange={(e) => updateLine(line.key, { package_id: e.target.value, design_id: "" })} required>
                        <option value="">Kind of mehndi…</option>
                        {packages.map((p) => (
                          <option key={p.id} value={p.id}>
                            {categoryLabel(p.package_type)} · {p.name}
                          </option>
                        ))}
                      </select>
                      <span className="flex items-center gap-2 text-sm">
                        <QuantityStepper value={line.quantity} onChange={(v) => updateLine(line.key, { quantity: v })} />
                        {Number(line.quantity) === 1 ? "person" : "people"}
                      </span>
                    </div>
                    {pkgDesigns.length > 0 && (
                      <select className="input" value={line.design_id} onChange={(e) => updateLine(line.key, { design_id: e.target.value })}>
                        <option value="">Any design from this package — or upload your own below</option>
                        {pkgDesigns.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name} ({formatPriceRange(d.price_min, d.price_max)})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {line.package_id && !line.design_id && (
                  <FileUpload
                    onFile={(f) => uploadFor(line.key, f)}
                    busy={uploadingKey === line.key}
                    previewUrl={line.reference_image_url}
                    label="Upload your own design for this group (optional)"
                  />
                )}
                <input
                  className="input"
                  value={line.note}
                  onChange={(e) => updateLine(line.key, { note: e.target.value })}
                  placeholder="Note for this group (optional) — e.g. bride, both hands to the elbow"
                  maxLength={500}
                />
                {band && (
                  <p className="text-xs flex flex-wrap gap-x-3 gap-y-1">
                    <span className="font-semibold text-maroon-soft">{formatPriceRange(band.price_min, band.price_max)} per person</span>
                    {pkg?.advance_amount > 0 && <span className="text-ink-soft">₹{pkg.advance_amount} deposit per person</span>}
                    {pkg && <span className="text-ink-soft">~{formatDuration(design?.duration_minutes || pkg.duration_minutes)} each</span>}
                  </p>
                )}
              </div>
            );
          })}

          <button
            type="button"
            className="rounded-2xl border-2 border-dashed border-line py-3 text-sm font-semibold text-maroon-soft hover:border-gold hover:bg-gold-soft/40 transition-colors disabled:opacity-50"
            onClick={() => setLines((prev) => [...prev, newLine()])}
            disabled={lines.length >= 20}
          >
            + Add another group
          </button>
        </section>

        <section className="flex flex-col gap-4">
          <StepHeading n={3} title="Final touches" />
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-sm font-semibold">Artist gender preference</span>
              <select className="input" value={genderPref} onChange={(e) => setGenderPref(e.target.value)}>
                <option value="same">Same as mine (recommended)</option>
                <option value="any">No preference</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-sm font-semibold">Anything else? (optional)</span>
              <input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Timings, theme colours, parking…" maxLength={2000} />
            </label>
          </div>
        </section>
      </div>

      <aside className="lg:sticky lg:top-24 flex flex-col gap-4">
        {s ? (
          <Receipt
            title={bulkOccasionLabel(occasion)}
            subtitle={eventAt ? new Date(eventAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "Your event estimate"}
            rows={[
              ...estimate.lines.map((l, i) => [`${l.quantity} × ${lineLabel(filled[i])}`, formatPriceRange(l.unit_price_min * l.quantity, l.unit_price_max * l.quantity)]),
              ["Platform fee", s.fee],
            ]}
            total={[`${estimate.people} ${estimate.people === 1 ? "person" : "people"}`, s.total]}
            footnotes={[
              "Our quote always lands inside this range — never above it.",
              s.deposit && `${s.deposit} deposit once you accept, refundable up to 24 hours before the event.`,
            ]}
          >
            {error && <p className="text-sm text-red-700 mt-3">{error}</p>}
            <button className="btn-primary w-full mt-4 py-3" disabled={submitting}>
              {submitting ? "Sending…" : "Request my quote"}
            </button>
            <p className="text-[11px] text-ink-soft text-center mt-2">No payment now — you only pay after accepting the quote.</p>
          </Receipt>
        ) : (
          <EmptyReceipt text="Add a group to see your event's estimate build up here." />
        )}
        {!s && error && <p className="text-sm text-red-700">{error}</p>}
      </aside>
    </form>
  );
}
