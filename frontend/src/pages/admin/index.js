import { useEffect, useState } from "react";
import FileUpload from "@/components/FileUpload";
import { api } from "@/lib/api";
import { BULK_STATUS_LABELS, DEPOSIT_LABELS, bulkOccasionLabel, estimateSummary, formatInr } from "@/lib/pricing";
import { CATEGORIES, COVERAGES, OCCASIONS, STYLES, categoryLabel, coverageLabel, formatDuration, formatPriceRange, groupByCategory, styleLabel } from "@/lib/designs";

const TABS = [
  "Overview",
  "Bookings",
  "Bulk Orders",
  "Disputes",
  "Users",
  "Artists",
  "Packages",
  "Designs",
  "Design Photos",
  "KYC Approvals",
  "Reports",
  "Shop Products",
  "Shop Orders",
  "Brand Content",
  "Settings",
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("Overview");

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl">Admin</h1>
      <div className="flex gap-2 flex-wrap">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={tab === t ? "btn-primary text-sm" : "btn-secondary text-sm"}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <OverviewTab />}
      {tab === "Bookings" && <AllBookingsTab />}
      {tab === "Bulk Orders" && <BulkOrdersTab />}
      {tab === "Disputes" && <DisputesTab />}
      {tab === "Designs" && <DesignsTab />}
      {tab === "Design Photos" && <DesignPhotosTab />}
      {tab === "Settings" && <SettingsTab />}
      {tab === "Users" && <UsersTab />}
      {tab === "Artists" && <ArtistsTab />}
      {tab === "Packages" && <PackagesTab />}
      {tab === "KYC Approvals" && <KycTab />}
      {tab === "Reports" && <ReportsTab />}
      {tab === "Shop Products" && <ShopProductsTab />}
      {tab === "Shop Orders" && <ShopOrdersTab />}
      {tab === "Brand Content" && <CmsTab />}
    </div>
  );
}

function OverviewTab() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/admin/overview").then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!stats) return <p className="text-sm text-ink-soft">Loading…</p>;

  const tiles = [
    { label: "Consumers", value: stats.total_consumers },
    { label: "Artists (approved)", value: `${stats.total_artists} (${stats.approved_artists})` },
    { label: "Pending KYC", value: stats.pending_kyc_count, accent: stats.pending_kyc_count > 0 },
    { label: "Total Bookings", value: stats.total_bookings },
    { label: "Completed Bookings", value: stats.completed_bookings },
    { label: "Open Reports", value: stats.open_reports_count, accent: stats.open_reports_count > 0 },
    { label: "Platform Revenue", value: `₹${stats.total_platform_revenue}` },
  ];

  return (
    <div className="grid sm:grid-cols-3 gap-3">
      {tiles.map((t) => (
        <div key={t.label} className="card p-4 text-center">
          <div className={`text-2xl font-semibold ${t.accent ? "text-red-700" : "text-maroon-soft"}`}>{t.value}</div>
          <div className="text-xs text-ink-soft mt-1">{t.label}</div>
        </div>
      ))}
    </div>
  );
}

const PAGE_SIZE = 50;

function AllBookingsTab() {
  const [bookings, setBookings] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  function load() {
    api
      .get("/admin/bookings", { status_filter: statusFilter, flagged_only: flaggedOnly, limit: PAGE_SIZE, offset: 0 })
      .then((rows) => {
        setBookings(rows);
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter, flaggedOnly]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const rows = await api.get("/admin/bookings", {
        status_filter: statusFilter,
        flagged_only: flaggedOnly,
        limit: PAGE_SIZE,
        offset: bookings.length,
      });
      setBookings((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-semibold">All Bookings</h2>
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-xs flex items-center gap-1.5">
            <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
            Far-away check-ins only
          </label>
          <select className="input w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {["all", "requested", "negotiating", "confirmed", "artist_enroute", "arrived", "in_progress", "design_uploaded", "completed", "disputed", "cancelled"].map((s) => (
              <option key={s} value={s}>
                {s.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-soft uppercase">
              <th className="pb-2 pr-3">Package</th>
              <th className="pb-2 pr-3">Consumer</th>
              <th className="pb-2 pr-3">Artist</th>
              <th className="pb-2 pr-3">Scheduled</th>
              <th className="pb-2 pr-3">Amount</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {bookings.map((b) => (
              <tr
                key={b.id}
                className="border-t border-line cursor-pointer hover:bg-ivory"
                onClick={() => window.open(`/booking-detail/${b.id}`, "_blank")}
              >
                <td className="py-2 pr-3">{b.package_name}</td>
                <td className="py-2 pr-3">{b.consumer_name || b.consumer_phone}</td>
                <td className="py-2 pr-3">{b.artist_name || b.artist_phone}</td>
                <td className="py-2 pr-3">{new Date(b.scheduled_at).toLocaleDateString()}</td>
                <td className="py-2 pr-3">{b.total_amount != null ? `₹${b.total_amount}` : "—"}</td>
                <td className="py-2">
                  <span className="chip">{b.status.replaceAll("_", " ")}</span>
                  {b.arrival_flagged && (
                    <span className="chip text-red-700 ml-1" title="Checked in far from the booking address">
                      ⚠ {(b.arrival_distance_m / 1000).toFixed(1)} km off
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {bookings.length === 0 && <p className="text-sm text-ink-soft py-3">No bookings.</p>}
      </div>
      {hasMore && (
        <button className="btn-secondary text-sm mt-3" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

function DisputesTab() {
  const [disputes, setDisputes] = useState(null);
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  function load() {
    api
      .get("/admin/disputes")
      .then(setDisputes)
      .catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function resolve(bookingId, outcome) {
    const confirmText =
      outcome === "released"
        ? "Release this booking? The consumer will be able to pay and complete it."
        : "Cancel this booking? No platform fee is charged and any paid advance is refunded.";
    if (!window.confirm(confirmText)) return;
    setBusyId(bookingId);
    setError("");
    try {
      await api.post(`/admin/bookings/${bookingId}/resolve-dispute`, { outcome, notes: notes[bookingId] || null });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (!disputes) return error ? <p className="text-sm text-red-700">{error}</p> : <p className="text-sm text-ink-soft">Loading…</p>;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-700">{error}</p>}
      {disputes.length === 0 && <p className="card p-5 text-sm text-ink-soft">No disputed bookings right now.</p>}
      {disputes.map((d) => (
        <div key={d.booking.id} className="card p-5 flex flex-col gap-3">
          <div className="flex justify-between items-start gap-2 flex-wrap">
            <div>
              <h2 className="font-semibold">{d.booking.package_name}</h2>
              <p className="text-xs text-ink-soft">
                {d.booking.consumer_name || d.booking.consumer_phone} → {d.booking.artist_name || d.booking.artist_phone} ·{" "}
                {new Date(d.booking.scheduled_at).toLocaleString()}
              </p>
              <p className="text-xs text-ink-soft">
                Total ₹{d.booking.total_amount ?? "—"}
                {d.advance_amount > 0 && ` · advance ₹${d.advance_amount} (${d.advance_status})`}
                {d.booking.arrival_flagged && ` · ⚠ checked in ${(d.booking.arrival_distance_m / 1000).toFixed(1)} km away`}
              </p>
            </div>
            <a href={`/booking-detail/${d.booking.id}`} target="_blank" rel="noreferrer" className="text-xs text-maroon-soft underline">
              Open booking
            </a>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              ["Reference design", d.reference_image_url],
              ["Finished design", d.completed_image_url],
            ].map(([label, url]) => (
              <figure key={label} className="flex flex-col gap-1">
                <figcaption className="text-xs font-semibold">{label}</figcaption>
                {url ? (
                  <img src={url} alt={label} className="rounded-lg border border-line object-cover aspect-square w-full" />
                ) : (
                  <div className="rounded-lg border-2 border-dashed border-line aspect-square flex items-center justify-center text-xs text-ink-soft">
                    {label === "Finished design" ? "Not uploaded yet" : "None chosen"}
                  </div>
                )}
              </figure>
            ))}
          </div>
          {d.similarity_score != null && <p className="text-sm">Match score: {d.similarity_score}%</p>}

          <div className="flex flex-col gap-1">
            <p className="text-xs font-semibold">Reports</p>
            {d.reports.length === 0 && <p className="text-xs text-ink-soft">None — the consumer rejected the design.</p>}
            {d.reports.map((r) => (
              <p key={r.id} className="text-sm">
                <b>{r.category.replaceAll("_", " ")}</b>
                {r.description && ` — ${r.description}`}
              </p>
            ))}
          </div>

          <textarea
            className="input"
            placeholder="Resolution notes (shown to both sides)"
            value={notes[d.booking.id] || ""}
            onChange={(e) => setNotes({ ...notes, [d.booking.id]: e.target.value })}
          />
          <div className="flex gap-2 flex-wrap">
            <button className="btn-primary text-sm" disabled={busyId === d.booking.id} onClick={() => resolve(d.booking.id, "released")}>
              Release booking
            </button>
            <button className="btn-secondary text-sm text-red-700" disabled={busyId === d.booking.id} onClick={() => resolve(d.booking.id, "cancelled")}>
              Cancel &amp; refund advance
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

const SETTING_FIELDS = [
  { key: "platform_fee_percent", label: "Platform fee (%)", hint: "Used when the fee mode is percent", step: "0.1" },
  { key: "platform_fee_flat", label: "Platform fee (flat ₹)", hint: "Used when the fee mode is flat", step: "1" },
  { key: "design_match_threshold", label: "Design auto-match threshold (%)", hint: "Scores at or above this release payment without asking the consumer", step: "1" },
  { key: "strikes_before_suspension", label: "Strikes before auto-suspension", hint: "Upheld reports that suspend an artist", step: "1" },
  { key: "checkin_flag_distance_m", label: "Check-in flag distance (m)", hint: "Check-ins farther than this from the address get flagged", step: "50" },
];

function SettingsTab() {
  const [values, setValues] = useState(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/admin/settings")
      .then(setValues)
      .catch((e) => setError(e.message));
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const payload = { platform_fee_mode: values.platform_fee_mode };
      for (const f of SETTING_FIELDS) payload[f.key] = Number(values[f.key]);
      setValues(await api.put("/admin/settings", payload));
      setSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!values) return error ? <p className="text-sm text-red-700">{error}</p> : <p className="text-sm text-ink-soft">Loading…</p>;

  return (
    <form onSubmit={save} className="card p-5 flex flex-col gap-4 max-w-xl">
      <div>
        <h2 className="font-semibold">Business Settings</h2>
        <p className="text-xs text-ink-soft">
          Changes apply immediately to new confirmations — fees on bookings that are already confirmed don&apos;t change.
        </p>
      </div>
      <label className="text-sm flex flex-col gap-1">
        Platform fee mode
        <select className="input" value={values.platform_fee_mode} onChange={(e) => setValues({ ...values, platform_fee_mode: e.target.value })}>
          <option value="percent">Percent of agreed price</option>
          <option value="flat">Flat amount per booking</option>
        </select>
      </label>
      {SETTING_FIELDS.map((f) => (
        <label key={f.key} className="text-sm flex flex-col gap-1">
          {f.label}
          <input
            className="input"
            type="number"
            step={f.step}
            value={values[f.key]}
            onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
            required
          />
          <span className="text-xs text-ink-soft">{f.hint}</span>
        </label>
      ))}
      {error && <p className="text-sm text-red-700">{error}</p>}
      {saved && <p className="text-sm text-leaf">Saved.</p>}
      <button className="btn-primary self-start" disabled={busy}>
        {busy ? "Saving…" : "Save settings"}
      </button>
    </form>
  );
}

const EMPTY_DESIGN = {
  package_id: "",
  name: "",
  description: "",
  price_min: "",
  price_max: "",
  duration_minutes: 60,
  sort_order: 0,
  style: "",
  coverage: "",
  occasions: [],
};

function DesignsTab() {
  const [designs, setDesigns] = useState(null);
  const [packages, setPackages] = useState([]);
  const [form, setForm] = useState(EMPTY_DESIGN);
  const [editingId, setEditingId] = useState(null);
  const [galleryFor, setGalleryFor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api
      .get("/designs/admin/all")
      .then(setDesigns)
      .catch((e) => setError(e.message));
  }
  useEffect(() => {
    load();
    api.get("/packages").then(setPackages).catch(() => {});
  }, []);

  function edit(d) {
    setEditingId(d.id);
    setForm({
      package_id: d.package_id,
      name: d.name,
      description: d.description || "",
      price_min: d.price_min,
      price_max: d.price_max,
      duration_minutes: d.duration_minutes,
      sort_order: d.sort_order,
      is_active: d.is_active,
      style: d.style || "",
      coverage: d.coverage || "",
      occasions: d.occasions || [],
      photo_needed: d.photo_needed,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function reset() {
    setEditingId(null);
    setForm(EMPTY_DESIGN);
  }

  async function run(fn, paths) {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      await revalidatePublicPages(["/", "/designs", ...paths(result)]);
      load();
      return result;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save(e) {
    e.preventDefault();
    const body = {
      ...form,
      price_min: Number(form.price_min),
      price_max: Number(form.price_max),
      duration_minutes: Number(form.duration_minutes),
      sort_order: Number(form.sort_order) || 0,
      description: form.description || null,
      is_active: form.is_active ?? true,
      style: form.style || null,
      coverage: form.coverage || null,
    };
    const saved = await run(
      () => (editingId ? api.put(`/designs/${editingId}`, body) : api.post("/designs", body)),
      (d) => [`/designs/${d.id}`]
    );
    if (saved) reset();
  }

  function uploadImage(id, file) {
    run(() => api.upload(`/designs/${id}/image`, file), () => [`/designs/${id}`]);
  }

  function setActive(d, active) {
    if (active && !d.image_url) {
      window.alert(`Add a main photo to "${d.name}" before showing it.`);
      return;
    }
    if (!active && !window.confirm(`Hide "${d.name}"? Existing bookings keep it; nobody can book it new.`)) return;
    run(
      () =>
        active
          ? api.put(`/designs/${d.id}`, { ...d, description: d.description || null, is_active: true, photo_needed: null })
          : api.del(`/designs/${d.id}`),
      () => [`/designs/${d.id}`]
    );
  }

  const selectedPackage = packages.find((p) => p.id === form.package_id);
  const needPhoto = (designs || []).filter((d) => !d.is_active && (d.photo_needed || !d.image_url));

  return (
    <div className="flex flex-col gap-4">
      {needPhoto.length > 0 && (
        <div className="card p-5 flex flex-col gap-3 border-l-4 border-gold">
          <div>
            <h2 className="font-semibold">Needs a photo ({needPhoto.length})</h2>
            <p className="text-xs text-ink-soft">
              Hidden from customers until they have a good real photo. Upload one here (or use an artist&apos;s approved photo
              from the Design Photos tab), then press Show. Photo tips: the hand or foot fills the frame, plain background,
              daylight, finished stain, no faces or real names.
            </p>
          </div>
          {needPhoto.map((d) => (
            <div key={d.id} className="border-t border-line pt-3 flex gap-3 items-center">
              <FileUpload variant="avatar" previewUrl={d.image_url} onFile={(f) => uploadImage(d.id, f)} busy={busy} label="Upload main photo" />
              <div className="flex-1 min-w-0 text-sm">
                <p className="font-semibold">
                  {d.name} <span className="chip text-[11px]">{categoryLabel(d.category)}</span>
                </p>
                {d.photo_needed && <p className="text-xs text-ink-soft">Needs: {d.photo_needed}</p>}
              </div>
              <button type="button" className="btn-secondary text-xs" disabled={busy || !d.image_url} onClick={() => setActive(d, true)}>
                Show
              </button>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={save} className="card p-5 grid sm:grid-cols-2 gap-3">
        <h2 className="font-semibold sm:col-span-2">{editingId ? "Edit design" : "Add a design"}</h2>
        <label className="text-sm flex flex-col gap-1">
          Category (package)
          <select className="input" value={form.package_id} onChange={(e) => setForm({ ...form, package_id: e.target.value })} required>
            <option value="">Select…</option>
            {packages.map((p) => (
              <option key={p.id} value={p.id}>
                {categoryLabel(p.package_type)} — {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm flex flex-col gap-1">
          Name
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={150} />
        </label>
        <label className="text-sm flex flex-col gap-1">
          Price from (₹)
          <input className="input" type="number" min="1" value={form.price_min} onChange={(e) => setForm({ ...form, price_min: e.target.value })} required />
        </label>
        <label className="text-sm flex flex-col gap-1">
          Price to (₹)
          <input
            className="input"
            type="number"
            min={form.price_min || 1}
            value={form.price_max}
            onChange={(e) => setForm({ ...form, price_max: e.target.value })}
            required
          />
        </label>
        <label className="text-sm flex flex-col gap-1">
          Duration (minutes)
          <input className="input" type="number" min="10" max="720" value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} required />
        </label>
        <label className="text-sm flex flex-col gap-1">
          Display order
          <input className="input" type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} />
        </label>
        <label className="text-sm flex flex-col gap-1">
          Style
          <select className="input" value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })}>
            <option value="">—</option>
            {STYLES.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm flex flex-col gap-1">
          Coverage
          <select className="input" value={form.coverage} onChange={(e) => setForm({ ...form, coverage: e.target.value })}>
            <option value="">—</option>
            {COVERAGES.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="text-sm flex flex-col gap-1 sm:col-span-2">
          <legend className="mb-1">Good for (occasions)</legend>
          <div className="flex gap-x-4 gap-y-1 flex-wrap">
            {OCCASIONS.map((o) => (
              <label key={o.key} className="flex gap-1 items-center text-xs">
                <input
                  type="checkbox"
                  checked={form.occasions.includes(o.key)}
                  onChange={(e) =>
                    setForm({ ...form, occasions: e.target.checked ? [...form.occasions, o.key] : form.occasions.filter((k) => k !== o.key) })
                  }
                />
                {o.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="text-sm flex flex-col gap-1 sm:col-span-2">
          Description
          <textarea className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={2000} />
        </label>
        {selectedPackage && (
          <p className="text-xs text-ink-soft sm:col-span-2">
            Package range for reference: {formatPriceRange(selectedPackage.price_min, selectedPackage.price_max)}. A booked design uses its own range
            for negotiation.
          </p>
        )}
        {error && <p className="text-sm text-red-700 sm:col-span-2">{error}</p>}
        <div className="flex gap-2 sm:col-span-2">
          <button className="btn-primary" disabled={busy}>
            {editingId ? "Save changes" : "Add design"}
          </button>
          {editingId && (
            <button type="button" className="btn-secondary" onClick={reset}>
              Cancel
            </button>
          )}
        </div>
        {!editingId && <p className="text-xs text-ink-soft sm:col-span-2">Add the design photo after saving.</p>}
      </form>

      {designs === null ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : designs.length === 0 ? (
        <p className="card p-5 text-sm text-ink-soft">No designs yet — add the first one above.</p>
      ) : (
        groupByCategory(designs).map(([cat, items]) => (
          <div key={cat} className="card p-5 flex flex-col gap-3">
            <h2 className="font-semibold">{categoryLabel(cat)}</h2>
            {items.map((d) => (
              <div key={d.id} className={`border-t border-line pt-3 ${d.is_active ? "" : "opacity-60"}`}>
                <div className="flex gap-3 items-center">
                  <FileUpload variant="avatar" previewUrl={d.image_url} onFile={(f) => uploadImage(d.id, f)} busy={busy} label="Replace main photo" />
                  <div className="flex-1 min-w-0 text-sm">
                    <p className="font-semibold">
                      {d.name} {!d.is_active && <span className="chip text-[11px]">hidden</span>}
                      {!d.image_url && <span className="chip text-[11px] text-red-700 ml-1">needs photo</span>}
                    </p>
                    <p className="text-ink-soft text-xs">
                      {formatPriceRange(d.price_min, d.price_max)} · {formatDuration(d.duration_minutes)} · {d.artist_count} artist
                      {d.artist_count === 1 ? "" : "s"}
                    </p>
                    {(d.style || d.coverage) && (
                      <p className="text-ink-soft text-xs">{[d.style && styleLabel(d.style), d.coverage && coverageLabel(d.coverage)].filter(Boolean).join(" · ")}</p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 items-end text-xs">
                    <button type="button" className="text-maroon-soft underline" onClick={() => setGalleryFor(galleryFor === d.id ? null : d.id)}>
                      Photos ({d.image_count})
                    </button>
                    <button type="button" className="text-maroon-soft underline" onClick={() => edit(d)}>
                      Edit
                    </button>
                    <button type="button" className="text-ink-soft underline" onClick={() => setActive(d, !d.is_active)} disabled={busy}>
                      {d.is_active ? "Hide" : "Show"}
                    </button>
                  </div>
                </div>
                {galleryFor === d.id && (
                  <DesignGalleryManager
                    design={d}
                    onChanged={async () => {
                      await revalidatePublicPages(["/", "/designs", `/designs/${d.id}`]);
                      load();
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );
}

const GALLERY_KINDS = [
  { key: "angle", label: "Another angle" },
  { key: "detail", label: "Close-up" },
  { key: "photo", label: "Photo" },
  { key: "illustration", label: "Illustration" },
  { key: "ai_photo", label: "Realistic AI preview" },
];

/** Admin view of one design's gallery: add labelled views, remove them,
 * or promote one to the main photo (the verification reference). */
function DesignGalleryManager({ design, onChanged }) {
  const [images, setImages] = useState(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState("angle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api
      .get(`/designs/${design.id}/gallery`)
      .then(setImages)
      .catch((e) => setError(e.message));
  }
  useEffect(load, [design.id]);

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      load();
      await onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function upload(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (label.trim()) form.append("label", label.trim());
    run(async () => {
      await api.uploadForm(`/designs/${design.id}/gallery`, form);
      setLabel("");
    });
  }

  return (
    <div className="mt-3 ml-1 sm:ml-28 flex flex-col gap-3 bg-ivory rounded-xl p-3">
      <p className="text-xs text-ink-soft">
        Customers see the main photo first, then these views in order. The main photo is also what finished work is checked
        against.
      </p>
      {error && <p className="text-xs text-red-700">{error}</p>}
      {images === null ? (
        <p className="text-xs text-ink-soft">Loading…</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
          {design.image_url && (
            <figure className="flex flex-col gap-1 text-[11px]">
              <img src={design.image_url} alt="Main photo" className="w-full aspect-square object-cover rounded-lg ring-2 ring-maroon" />
              <figcaption className="font-semibold">Main photo</figcaption>
            </figure>
          )}
          {images.map((img) => (
            <figure key={img.id} className="flex flex-col gap-1 text-[11px]">
              <img src={img.url} alt={img.label || img.kind} className="w-full aspect-square object-cover rounded-lg border border-line" />
              <figcaption className="leading-tight">
                {img.label || img.kind}
                <span className="block text-ink-soft">{img.kind}</span>
              </figcaption>
              <div className="flex gap-2">
                {img.kind !== "ai_photo" && (
                  <button
                    type="button"
                    className="text-maroon-soft underline"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm("Make this the main photo? New bookings will be verified against it.")) {
                        run(() => api.post(`/designs/${design.id}/gallery/${img.id}/make-main`, {}));
                      }
                    }}
                  >
                    Make main
                  </button>
                )}
                <button
                  type="button"
                  className="text-red-700 underline"
                  disabled={busy}
                  onClick={() => window.confirm("Remove this view?") && run(() => api.del(`/designs/${design.id}/gallery/${img.id}`))}
                >
                  Remove
                </button>
              </div>
            </figure>
          ))}
        </div>
      )}
      <div className="border-t border-line pt-3 flex flex-wrap gap-3 items-center text-xs">
        <span>
          <b>360° view:</b>{" "}
          {design.spin_frame_count >= 8 ? `${design.spin_frame_count} frames` : "none yet"}
        </span>
        <label className={`btn-secondary text-xs cursor-pointer ${busy ? "opacity-50 pointer-events-none" : ""}`}>
          {design.spin_frame_count ? "Replace 360 frames" : "Upload 360 frames"}
          <input
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = [...e.target.files];
              e.target.value = "";
              if (!files.length) return;
              const form = new FormData();
              files.forEach((f) => form.append("files", f));
              run(() => api.uploadForm(`/designs/${design.id}/spin`, form, "PUT"));
            }}
          />
        </label>
        {design.spin_frame_count > 0 && (
          <button type="button" className="text-red-700 underline" disabled={busy} onClick={() => window.confirm("Remove the 360 view?") && run(() => api.del(`/designs/${design.id}/spin`))}>
            Remove 360 view
          </button>
        )}
        <span className="text-ink-soft basis-full">
          Turntable photos of the real design, 8-72 frames taken every 5-15° all the way round, named in order (01.jpg, 02.jpg…).
        </span>
      </div>
      <div className="flex flex-wrap gap-2 items-end">
        <label className="text-xs flex flex-col gap-1">
          Type
          <select className="input py-1.5" value={kind} onChange={(e) => setKind(e.target.value)}>
            {GALLERY_KINDS.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs flex flex-col gap-1 flex-1 min-w-[10rem]">
          Label (optional)
          <input className="input py-1.5" value={label} maxLength={80} placeholder="e.g. Side view, Palm close-up" onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className={`btn-secondary text-xs cursor-pointer ${busy ? "opacity-50 pointer-events-none" : ""}`}>
          {busy ? "Uploading…" : "Add photo"}
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files[0];
              e.target.value = "";
              if (f) upload(f);
            }}
          />
        </label>
      </div>
    </div>
  );
}

function DesignPhotosTab() {
  const [statusFilter, setStatusFilter] = useState("pending");
  const [rows, setRows] = useState(null);
  const [reasons, setReasons] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  function load() {
    api
      .get("/admin/design-photos", { status_filter: statusFilter })
      .then(setRows)
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter]);

  async function review(row, action) {
    setBusyId(row.id);
    setError("");
    try {
      if (action === "approve") await api.post(`/admin/design-photos/${row.id}/approve`, {});
      else if (action === "catalog") await api.post(`/admin/design-photos/${row.id}/use-as-catalog`, {});
      else await api.post(`/admin/design-photos/${row.id}/reject`, { reason: reasons[row.id] || "" });
      await revalidatePublicPages(["/designs", `/designs/${row.design.id}`]);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm text-ink-soft max-w-xl">
          Check each photo is genuinely this artist&apos;s work of the catalog design — approved photos appear publicly on
          the design page and let customers book the artist for it.
        </p>
        <select className="input w-40 flex-none" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {["pending", "approved", "rejected", "all"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {rows === null && <p className="text-sm text-ink-soft">Loading…</p>}
      {rows?.length === 0 && <p className="card p-5 text-sm text-ink-soft">Nothing {statusFilter === "all" ? "" : statusFilter} right now.</p>}
      {rows?.map((r) => (
        <div key={r.id} className="card p-5 flex flex-col gap-3">
          <div className="flex justify-between gap-2 flex-wrap text-sm">
            <span>
              <b>{r.artist_name || r.artist_phone}</b> · {r.design.name} ({categoryLabel(r.design.category)})
            </span>
            <span className="chip">{r.status}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 max-w-lg">
            <figure className="flex flex-col gap-1">
              <img src={r.proof_image_url} alt="Artist's photo" className="rounded-lg border border-line aspect-square object-cover w-full" />
              <figcaption className="text-xs text-ink-soft text-center">Artist&apos;s photo</figcaption>
            </figure>
            <figure className="flex flex-col gap-1">
              {r.design.image_url ? (
                <img src={r.design.image_url} alt="Catalog design" className="rounded-lg border border-line aspect-square object-cover w-full" />
              ) : (
                <div className="rounded-lg border-2 border-dashed border-line aspect-square" />
              )}
              <figcaption className="text-xs text-ink-soft text-center">Catalog design</figcaption>
            </figure>
          </div>
          {r.rejection_reason && <p className="text-xs text-red-700">Rejected: {r.rejection_reason}</p>}
          {r.design.image_url === r.proof_image_url ? (
            <p className="text-xs text-leaf">★ This photo is the design&apos;s catalog photo</p>
          ) : r.catalog_consent ? (
            <div className="flex gap-2 items-center flex-wrap text-xs">
              <span className="chip text-leaf">Artist allows catalog use</span>
              {r.status === "approved" && (
                <button
                  className="btn-secondary text-sm"
                  disabled={busyId === r.id}
                  onClick={() => {
                    if (window.confirm("Make this the design's main catalog photo? The current one stays in the gallery.")) review(r, "catalog");
                  }}
                >
                  Use as catalog photo
                </button>
              )}
            </div>
          ) : null}
          {r.status !== "approved" || statusFilter === "all" ? (
            <div className="flex gap-2 flex-wrap items-center">
              {r.status !== "approved" && (
                <button className="btn-primary text-sm" disabled={busyId === r.id} onClick={() => review(r, "approve")}>
                  Approve
                </button>
              )}
              {r.status !== "rejected" && (
                <>
                  <input
                    className="input flex-1 min-w-[12rem]"
                    placeholder="Reason for rejecting (shown to the artist)"
                    value={reasons[r.id] || ""}
                    onChange={(e) => setReasons({ ...reasons, [r.id]: e.target.value })}
                  />
                  <button
                    className="btn-secondary text-sm text-red-700"
                    disabled={busyId === r.id || (reasons[r.id] || "").trim().length < 3}
                    onClick={() => review(r, "reject")}
                  >
                    Reject
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="flex gap-2 items-center">
              <input
                className="input flex-1"
                placeholder="Reason, if this approval was a mistake"
                value={reasons[r.id] || ""}
                onChange={(e) => setReasons({ ...reasons, [r.id]: e.target.value })}
              />
              <button
                className="btn-secondary text-sm text-red-700"
                disabled={busyId === r.id || (reasons[r.id] || "").trim().length < 3}
                onClick={() => review(r, "reject")}
              >
                Revoke
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  function load() {
    const query = { limit: PAGE_SIZE, offset: 0 };
    if (role) query.role = role;
    if (search) query.search = search;
    api
      .get("/admin/users", query)
      .then((rows) => {
        setUsers(rows);
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, [role]);

  async function loadMore() {
    setLoadingMore(true);
    const query = { limit: PAGE_SIZE, offset: users.length };
    if (role) query.role = role;
    if (search) query.search = search;
    try {
      const rows = await api.get("/admin/users", query);
      setUsers((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  }

  async function toggleActive(u) {
    try {
      await api.post(`/admin/users/${u.id}/${u.is_active ? "suspend" : "reactivate"}`, {});
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-semibold">All Users</h2>
        <div className="flex gap-2">
          <select className="input w-auto" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">All roles</option>
            <option value="consumer">Consumers</option>
            <option value="artist">Artists</option>
            <option value="admin">Admins</option>
          </select>
          <input className="input w-auto" placeholder="Search name/phone" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
          <button className="btn-secondary text-sm" onClick={load}>
            Search
          </button>
        </div>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-2 text-sm">
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between border-b border-line pb-2">
            <div>
              <b>{u.name || "—"}</b> · {u.phone} · <span className="chip">{u.role}</span>
              {!u.is_active && <span className="chip ml-1 text-red-700">suspended</span>}
            </div>
            {u.role !== "admin" && (
              <button className="text-xs text-red-700" onClick={() => toggleActive(u)}>
                {u.is_active ? "Suspend" : "Reactivate"}
              </button>
            )}
          </div>
        ))}
        {users.length === 0 && <p className="text-sm text-ink-soft">No users found.</p>}
      </div>
      {hasMore && (
        <button className="btn-secondary text-sm mt-3" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

const ARTIST_PAGE_SIZE = 50;

function ArtistsTab() {
  const [artists, setArtists] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  function load() {
    const query = { status_filter: statusFilter, limit: ARTIST_PAGE_SIZE, offset: 0 };
    if (search) query.search = search;
    api
      .get("/admin/artists", query)
      .then((rows) => {
        setArtists(rows);
        setHasMore(rows.length === ARTIST_PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter]);

  async function loadMore() {
    setLoadingMore(true);
    const query = { status_filter: statusFilter, limit: ARTIST_PAGE_SIZE, offset: artists.length };
    if (search) query.search = search;
    try {
      const rows = await api.get("/admin/artists", query);
      setArtists((prev) => [...prev, ...rows]);
      setHasMore(rows.length === ARTIST_PAGE_SIZE);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  }

  async function toggleSuspend(a) {
    try {
      await api.post(`/admin/artists/${a.user_id}/${a.is_suspended ? "reactivate" : "suspend"}`, {});
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-semibold">Artists</h2>
        <div className="flex gap-2">
          <select className="input w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All KYC statuses</option>
            <option value="approved">Approved</option>
            <option value="pending">Pending</option>
            <option value="rejected">Rejected</option>
          </select>
          <input className="input w-auto" placeholder="Search name/phone" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
          <button className="btn-secondary text-sm" onClick={load}>
            Search
          </button>
        </div>
      </div>
      {error && <p className="text-sm text-red-700 mb-2">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-soft uppercase">
              <th className="pb-2 pr-3">Artist</th>
              <th className="pb-2 pr-3">KYC</th>
              <th className="pb-2 pr-3">Rating</th>
              <th className="pb-2 pr-3">Completed</th>
              <th className="pb-2 pr-3">Earnings</th>
              <th className="pb-2 pr-3">Strikes</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {artists.map((a) => (
              <tr key={a.user_id} className="border-t border-line">
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <img src={a.profile_photo_url || "/avatars/preset-1.svg"} alt="" className="h-7 w-7 rounded-full object-cover border border-line" />
                    <div>
                      <div className="font-semibold">{a.name || "—"}</div>
                      <div className="text-xs text-ink-soft">{a.phone}</div>
                    </div>
                  </div>
                </td>
                <td className="py-2 pr-3">
                  <span className="chip">{a.kyc_status}</span>
                  {a.is_suspended && <span className="chip ml-1 text-red-700">suspended</span>}
                </td>
                <td className="py-2 pr-3">{a.rating_count > 0 ? `★ ${a.rating_avg} (${a.rating_count})` : "—"}</td>
                <td className="py-2 pr-3">{a.completed_bookings}</td>
                <td className="py-2 pr-3">₹{a.total_earnings}</td>
                <td className="py-2 pr-3">{a.strike_count}</td>
                <td className="py-2">
                  <button className={`text-xs ${a.is_suspended ? "text-leaf" : "text-red-700"}`} onClick={() => toggleSuspend(a)}>
                    {a.is_suspended ? "Reactivate" : "Suspend"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {artists.length === 0 && <p className="text-sm text-ink-soft py-3">No artists found.</p>}
      </div>
      {hasMore && (
        <button className="btn-secondary text-sm mt-3" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

function PackagesTab() {
  const [packages, setPackages] = useState([]);
  const [form, setForm] = useState({ name: "", package_type: "regular", description: "", price_min: "", price_max: "", duration_minutes: 60, negotiable: true, sample_image_urls: "", advance_amount: "" });
  const [error, setError] = useState("");

  function load() {
    api.get("/packages").then(setPackages).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function submit(e) {
    e.preventDefault();
    try {
      await api.post("/packages", {
        ...form,
        price_min: Number(form.price_min),
        price_max: Number(form.price_max),
        duration_minutes: Number(form.duration_minutes),
        advance_amount: Number(form.advance_amount || 0),
      });
      setForm({ name: "", package_type: "regular", description: "", price_min: "", price_max: "", duration_minutes: 60, negotiable: true, sample_image_urls: "", advance_amount: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3">Packages</h2>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <form onSubmit={submit} className="grid sm:grid-cols-2 gap-2 mb-4">
        <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <select className="input" value={form.package_type} onChange={(e) => setForm({ ...form, package_type: e.target.value })}>
          {CATEGORIES.map((c) => (
            <option key={c.key} value={c.key}>
              {c.key === "feet" ? "Feet-only" : c.label}
            </option>
          ))}
        </select>
        <input className="input sm:col-span-2" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <input className="input" type="number" placeholder="Min price" value={form.price_min} onChange={(e) => setForm({ ...form, price_min: e.target.value })} required />
        <input className="input" type="number" placeholder="Max price" value={form.price_max} onChange={(e) => setForm({ ...form, price_max: e.target.value })} required />
        <input className="input" type="number" placeholder="Duration (minutes)" value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} />
        <input
          className="input"
          type="number"
          placeholder="Advance/booking deposit ₹ (0 = none)"
          value={form.advance_amount}
          onChange={(e) => setForm({ ...form, advance_amount: e.target.value })}
        />
        <input className="input sm:col-span-2" placeholder="Sample image URLs, comma-separated" value={form.sample_image_urls} onChange={(e) => setForm({ ...form, sample_image_urls: e.target.value })} />
        <button className="btn-primary sm:col-span-2">Add Package</button>
      </form>
      <div className="flex flex-col gap-4 text-sm">
        {packages.map((p) => (
          <PackageRow key={p.id} pkg={p} onChanged={load} />
        ))}
      </div>
    </div>
  );
}

function PackageRow({ pkg, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const images = (pkg.sample_image_urls || "").split(",").filter(Boolean);

  async function uploadPhoto(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api.upload(`/packages/${pkg.id}/images`, file);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function removePhoto(url) {
    setBusy(true);
    setError("");
    try {
      await api.del(`/packages/${pkg.id}/images?url=${encodeURIComponent(url)}`);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-line pb-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <b>{pkg.name}</b> ({pkg.package_type}) — ₹{pkg.price_min}–₹{pkg.price_max}, {pkg.duration_minutes} min
          {pkg.advance_amount > 0 && <span className="chip ml-2">₹{pkg.advance_amount} advance</span>}
        </div>
        <label className="btn-secondary text-xs cursor-pointer">
          {busy ? "Uploading..." : "Upload real photo"}
          <input type="file" accept="image/*" onChange={uploadPhoto} disabled={busy} className="hidden" />
        </label>
      </div>
      {error && <p className="text-xs text-red-700 mt-1">{error}</p>}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap mt-2">
          {images.map((url) => (
            <div key={url} className="relative">
              <img src={url} alt="" className="w-16 h-16 object-cover rounded-lg border border-line" />
              <button
                onClick={() => removePhoto(url)}
                className="absolute -top-1.5 -right-1.5 bg-maroon text-ivory-raised text-[10px] w-4 h-4 rounded-full leading-none"
                title="Remove"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ShopProductsTab() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", price: "", stock_quantity: "" });
  const [error, setError] = useState("");

  function load() {
    api.get("/shop/admin/products").then(setProducts).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function submit(e) {
    e.preventDefault();
    try {
      await api.post("/shop/products", {
        ...form,
        price: Number(form.price),
        stock_quantity: Number(form.stock_quantity || 0),
      });
      setForm({ name: "", description: "", price: "", stock_quantity: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function deactivate(id) {
    try {
      await api.del(`/shop/products/${id}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-1">Shop Products</h2>
      <p className="text-xs text-ink-soft mb-3">
        {products.filter((p) => p.is_active).length} live, {products.filter((p) => !p.is_active).length} drafts. Henna, hair and skin products need
        their manufacturing licence number (AYUSH, or cosmetic licence) entered before they can be published. Set stock for each pack size.
      </p>
      {error && <p className="text-sm text-red-700 mb-2">{error}</p>}
      <form onSubmit={submit} className="grid sm:grid-cols-2 gap-2 mb-4">
        <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <input className="input" type="number" placeholder="Price (₹)" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required />
        <input className="input sm:col-span-2" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <input className="input" type="number" placeholder="Stock quantity" value={form.stock_quantity} onChange={(e) => setForm({ ...form, stock_quantity: e.target.value })} />
        <button className="btn-primary sm:col-span-2">Add Product</button>
      </form>
      <div className="flex flex-col gap-4 text-sm">
        {products.map((p) => (
          <ShopProductRow key={p.id} product={p} onChanged={load} onDeactivate={() => deactivate(p.id)} />
        ))}
        {products.length === 0 && <p className="text-ink-soft">No products yet.</p>}
      </div>
    </div>
  );
}

function ShopProductRow({ product, onChanged, onDeactivate }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [licence, setLicence] = useState(product.licence_number || "");
  const [stock, setStock] = useState(() => Object.fromEntries((product.variants || []).map((v) => [v.id, String(v.stock_quantity)])));
  const images = (product.image_urls || "").split(",").filter(Boolean);
  const variants = (product.variants || []).filter((v) => v.is_active);
  const needsLicence = product.requires_licence && !(product.licence_number || "").trim();

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadPhoto(e) {
    const file = e.target.files[0];
    if (!file) return;
    await run(() => api.upload(`/shop/products/${product.id}/image`, file));
    e.target.value = "";
  }

  const removePhoto = (url) => run(() => api.del(`/shop/products/${product.id}/image?url=${encodeURIComponent(url)}`));
  const saveLicence = () => run(() => api.put(`/shop/products/${product.id}`, { name: product.name, price: product.price, licence_number: licence.trim() || null }));
  const publish = () => run(() => api.post(`/shop/products/${product.id}/publish`, {}));
  const saveStock = (v) => run(() => api.put(`/shop/variants/${v.id}/stock`, { stock_quantity: Number(stock[v.id] || 0) }));

  return (
    <div className="border-b border-line pb-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <b>{product.name}</b> — {variants.length ? `from ₹${product.price}` : `₹${product.price}, ${product.stock_quantity} in stock`}
          {product.is_active ? <span className="chip ml-2">live</span> : <span className="chip ml-2 text-red-700">draft</span>}
          {needsLicence && <span className="chip ml-2 text-red-700">licence no. needed</span>}
          {product.image_kind === "illustrative" && <span className="chip ml-2">illustrative image</span>}
        </div>
        <div className="flex gap-2 items-center">
          <label className="btn-secondary text-xs cursor-pointer" title={product.image_kind === "illustrative" ? "A real photo replaces the illustrative image" : undefined}>
            {busy ? "Saving..." : "Upload photo"}
            <input type="file" accept="image/*" onChange={uploadPhoto} disabled={busy} className="hidden" />
          </label>
          {product.is_active ? (
            <button className="text-xs text-red-700" onClick={onDeactivate}>
              Unpublish
            </button>
          ) : (
            <button className="btn-primary text-xs" onClick={publish} disabled={busy || needsLicence}>
              Publish
            </button>
          )}
        </div>
      </div>
      {product.requires_licence && (
        <div className="flex gap-2 items-center mt-2 max-w-md">
          <input className="input text-xs" placeholder="Manufacturing licence no. (printed on pack)" value={licence} onChange={(e) => setLicence(e.target.value)} />
          <button className="btn-secondary text-xs" onClick={saveLicence} disabled={busy || licence === (product.licence_number || "")}>
            Save
          </button>
        </div>
      )}
      {variants.length > 0 && (
        <div className="flex gap-3 flex-wrap mt-2">
          {variants.map((v) => (
            <div key={v.id} className="flex items-center gap-1 text-xs">
              <span className="font-semibold">{v.label}</span> ₹{v.price}
              <input
                className="input text-xs !w-16 !py-1"
                type="number"
                min="0"
                aria-label={`Stock for ${v.label}`}
                value={stock[v.id] ?? ""}
                onChange={(e) => setStock({ ...stock, [v.id]: e.target.value })}
              />
              {stock[v.id] !== String(v.stock_quantity) && (
                <button className="text-gold font-semibold" onClick={() => saveStock(v)} disabled={busy}>
                  Save
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-red-700 mt-1">{error}</p>}
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap mt-2">
          {images.map((url) => (
            <div key={url} className="relative">
              <img src={url} alt="" className="w-16 h-16 object-cover rounded-lg border border-line" />
              <button
                onClick={() => removePhoto(url)}
                className="absolute -top-1.5 -right-1.5 bg-maroon text-ivory-raised text-[10px] w-4 h-4 rounded-full leading-none"
                title="Remove"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const SHOP_ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled"];

function ShopOrdersTab() {
  const [orders, setOrders] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const PAGE_SIZE = 50;

  function load() {
    api
      .get("/admin/shop-orders", { status_filter: statusFilter, limit: PAGE_SIZE, offset: 0 })
      .then((rows) => {
        setOrders(rows);
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const rows = await api.get("/admin/shop-orders", { status_filter: statusFilter, limit: PAGE_SIZE, offset: orders.length });
      setOrders((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  async function updateStatus(id, status) {
    try {
      await api.post(`/admin/shop-orders/${id}/status`, { status });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-semibold">Shop Orders</h2>
        <select className="input w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {["all", ...SHOP_ORDER_STATUSES].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-3 text-sm">
        {orders.map((o) => (
          <div key={o.id} className="border-b border-line pb-3">
            <div className="flex justify-between items-start gap-2 flex-wrap">
              <div>
                <p className="font-semibold">{o.shipping_name} — ₹{o.total_amount}</p>
                <p className="text-xs text-ink-soft">{o.shipping_phone} · {o.shipping_address}</p>
                <p className="text-xs text-ink-soft mt-1">
                  {o.items.map((i) => `${i.product_name}${i.variant_label ? ` (${i.variant_label})` : ""} ×${i.quantity}`).join(", ")}
                </p>
              </div>
              <select className="input w-auto" value={o.status} onChange={(e) => updateStatus(o.id, e.target.value)}>
                {SHOP_ORDER_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}
        {orders.length === 0 && <p className="text-ink-soft">No orders yet.</p>}
      </div>
      {hasMore && (
        <button className="btn-secondary text-sm mt-3" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

function BulkOrdersTab() {
  const [orders, setOrders] = useState([]);
  const [statusFilter, setStatusFilter] = useState("requested");
  const [error, setError] = useState("");

  function load() {
    api
      .get("/admin/bulk-orders", { status_filter: statusFilter, limit: 200 })
      .then(setOrders)
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter]);

  function replace(updated) {
    setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <h2 className="font-semibold">Bulk / Event Orders</h2>
        <select className="input w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {["all", ...Object.keys(BULK_STATUS_LABELS)].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <p className="text-xs text-ink-soft mb-3">
        Quote each group at a per-person price inside its range — the same range as booking on their own. The platform fee is
        added per person automatically.
      </p>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-4">
        {orders.map((o) => (
          <BulkOrderRow key={o.id} order={o} onChanged={replace} />
        ))}
        {orders.length === 0 && <p className="text-sm text-ink-soft">No orders here.</p>}
      </div>
    </div>
  );
}

function BulkOrderRow({ order, onChanged }) {
  const [prices, setPrices] = useState(() => Object.fromEntries(order.lines.map((l) => [l.id, l.unit_price ?? l.unit_price_min])));
  const [note, setNote] = useState(order.admin_note || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const est = estimateSummary(order.estimate);
  const canQuote = ["requested", "quoted"].includes(order.status);

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      onChanged(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function sendQuote() {
    act(() =>
      api.post(`/admin/bulk-orders/${order.id}/quote`, {
        lines: order.lines.map((l) => ({ line_id: l.id, unit_price: Number(prices[l.id]) })),
        admin_note: note || null,
      })
    );
  }

  function cancel() {
    const reason = window.prompt("Reason for cancelling (sent to the customer). Any paid deposit is refunded in full.");
    if (reason !== null) act(() => api.post(`/admin/bulk-orders/${order.id}/cancel`, { reason: reason || null }));
  }

  return (
    <div className="border border-line rounded-xl p-4 text-sm flex flex-col gap-2">
      <div className="flex justify-between items-start gap-2 flex-wrap">
        <div>
          <p className="font-semibold">
            {bulkOccasionLabel(order.occasion)} · {order.people} people · {new Date(order.event_at + "Z").toLocaleString()}
          </p>
          <p className="text-xs text-ink-soft">
            {order.consumer_name || "Customer"} · {order.consumer_phone} · {order.address_text} · artist gender:{" "}
            {order.gender_preference === "same" ? "same as customer" : "any"}
          </p>
          {order.notes && <p className="text-xs mt-1">“{order.notes}”</p>}
        </div>
        <div className="flex gap-1 flex-wrap">
          <span className="chip">{BULK_STATUS_LABELS[order.status]}</span>
          {order.advance_amount > 0 && <span className="chip">{DEPOSIT_LABELS[order.advance_status]} {formatInr(order.advance_amount)}</span>}
        </div>
      </div>

      {order.lines.map((l) => (
        <div key={l.id} className="flex items-center gap-3 flex-wrap">
          {(l.design_image_url || l.reference_image_url) && (
            <a href={l.design_image_url || l.reference_image_url} target="_blank" rel="noreferrer">
              <img src={l.design_image_url || l.reference_image_url} alt="" className="w-12 h-12 rounded-lg object-cover border border-line" />
            </a>
          )}
          <div className="flex-1 min-w-[12rem]">
            <p>
              <b>{l.quantity} ×</b> {l.design_name || l.package_name} <span className="text-ink-soft">({categoryLabel(l.category)})</span>
              {l.reference_image_url && <span className="chip ml-1">own design</span>}
            </p>
            {l.note && <p className="text-xs text-ink-soft">{l.note}</p>}
          </div>
          <label className="text-xs flex items-center gap-1">
            ₹/person
            <input
              type="number"
              className="input w-28"
              min={l.unit_price_min}
              max={l.unit_price_max}
              value={prices[l.id]}
              disabled={!canQuote}
              onChange={(e) => setPrices({ ...prices, [l.id]: e.target.value })}
            />
            <span className="text-ink-soft">{formatPriceRange(l.unit_price_min, l.unit_price_max)}</span>
          </label>
        </div>
      ))}

      <p className="text-xs text-ink-soft">
        Estimate {est.total} (fee {est.fee})
        {order.total_amount != null && (
          <>
            {" "}· Quoted <b className="text-ink">{formatInr(order.total_amount)}</b> ({formatInr(order.subtotal)} + {formatInr(order.platform_fee)} fee)
          </>
        )}
      </p>

      {canQuote && (
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note to the customer (artists lined up, timings…)" />
      )}
      {error && <p className="text-red-700">{error}</p>}
      <div className="flex gap-2 flex-wrap">
        {canQuote && (
          <button className="btn-primary text-sm" disabled={busy} onClick={sendQuote}>
            {order.status === "quoted" ? "Update quote" : "Send quote"}
          </button>
        )}
        {order.status === "confirmed" && (
          <button className="btn-primary text-sm" disabled={busy || order.advance_status === "pending"} onClick={() => act(() => api.post(`/admin/bulk-orders/${order.id}/complete`, {}))}>
            Mark completed
          </button>
        )}
        {!["completed", "cancelled"].includes(order.status) && (
          <button className="btn-secondary text-sm" disabled={busy} onClick={cancel}>
            Cancel order
          </button>
        )}
      </div>
    </div>
  );
}

function KycTab() {
  const [pending, setPending] = useState([]);
  const [error, setError] = useState("");

  function load() {
    api.get("/admin/artists/pending-kyc").then(setPending).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function decide(id, decision) {
    try {
      await api.post(`/admin/artists/${id}/kyc/${decision}`, {});
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3">Pending KYC</h2>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-3">
        {pending.map((p) => (
          <div key={p.user_id} className="border-b border-line pb-3">
            <p className="font-semibold">{p.user.name || p.user.phone}</p>
            {p.date_of_birth && <p className="text-xs text-ink-soft">DOB: {p.date_of_birth}</p>}
            {p.guardian_name && <p className="text-xs text-ink-soft">Father/Husband: {p.guardian_name}</p>}
            <div className="flex gap-3 text-sm mt-1 flex-wrap">
              {p.kyc_selfie_url && <a className="underline" href={p.kyc_selfie_url} target="_blank" rel="noreferrer">Selfie</a>}
              {p.id_proof_doc_url && (
                <a className="underline" href={p.id_proof_doc_url} target="_blank" rel="noreferrer">
                  {(p.id_proof_type || "ID proof").replaceAll("_", " ")}{p.id_proof_number ? ` (${p.id_proof_number})` : ""}
                </a>
              )}
              {p.pan_doc_url && <a className="underline" href={p.pan_doc_url} target="_blank" rel="noreferrer">PAN{p.pan_number ? ` (${p.pan_number})` : ""}</a>}
              {p.address_proof_doc_url && <a className="underline" href={p.address_proof_doc_url} target="_blank" rel="noreferrer">Address proof</a>}
            </div>
            {(p.bank_account_number || p.bank_ifsc_code) && (
              <p className="text-xs text-ink-soft mt-1">
                Bank: {p.bank_account_holder_name}, A/C {p.bank_account_number}, IFSC {p.bank_ifsc_code}
              </p>
            )}
            {!p.consent_given && <p className="text-xs text-red-700 mt-1">Consent not yet given by artist.</p>}
            <div className="flex gap-2 mt-2">
              <button className="btn-primary text-xs" onClick={() => decide(p.user_id, "approve")}>
                Approve
              </button>
              <button className="text-xs text-red-700" onClick={() => decide(p.user_id, "reject")}>
                Reject
              </button>
            </div>
          </div>
        ))}
        {pending.length === 0 && <p className="text-sm text-ink-soft">Nothing pending.</p>}
      </div>
    </div>
  );
}

function ReportsTab() {
  const [reports, setReports] = useState([]);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  function load() {
    api
      .get("/admin/reports", { status_filter: "open", limit: PAGE_SIZE, offset: 0 })
      .then((rows) => {
        setReports(rows);
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const rows = await api.get("/admin/reports", { status_filter: "open", limit: PAGE_SIZE, offset: reports.length });
      setReports((prev) => [...prev, ...rows]);
      setHasMore(rows.length === PAGE_SIZE);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  }

  async function resolve(id, status, strike) {
    try {
      await api.post(`/admin/reports/${id}/resolve`, { status, strike_artist: strike, resolution_notes: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3">Open Reports</h2>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-col gap-3">
        {reports.map((r) => (
          <div key={r.id} className="border-b border-line pb-3 text-sm">
            <p>
              <b>{r.category}</b> — {r.description}
            </p>
            <div className="flex gap-2 mt-2">
              <button className="btn-primary text-xs" onClick={() => resolve(r.id, "resolved", true)}>
                Resolve + Strike Artist
              </button>
              <button className="btn-secondary text-xs" onClick={() => resolve(r.id, "resolved", false)}>
                Resolve, No Strike
              </button>
              <button className="text-xs text-ink-soft" onClick={() => resolve(r.id, "dismissed", false)}>
                Dismiss
              </button>
            </div>
          </div>
        ))}
        {reports.length === 0 && <p className="text-sm text-ink-soft">No open reports.</p>}
      </div>
      {hasMore && (
        <button className="btn-secondary text-sm mt-3" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

/** Rebuilds the server-rendered home page right away (on-demand ISR - see
 * pages/api/revalidate.js). A failure only means the page refreshes on
 * its normal schedule, so it never blocks the save. */
async function revalidatePublicPages(paths = ["/"]) {
  try {
    await api.post("/revalidate", { paths });
  } catch {
    /* falls back to the timed revalidation */
  }
}

function CmsHistory({ cmsKey, version, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get(`/cms/${cmsKey}/versions`).then(setVersions).catch(() => {});
  }, [open, cmsKey, version]);

  async function restore(id) {
    if (!window.confirm("Restore this version? It becomes the live content.")) return;
    const row = await api.post(`/cms/${cmsKey}/versions/${id}/restore`, {});
    await revalidatePublicPages();
    onRestored(row.content);
  }

  return (
    <details className="text-xs" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-ink-soft">Version history</summary>
      <ul className="mt-2 flex flex-col gap-1">
        {versions.map((v, i) => (
          <li key={v.id} className="flex justify-between gap-2 border-b border-line pb-1">
            <span>
              {new Date(v.created_at + "Z").toLocaleString()} · {v.updated_by || "unknown"}
              {i === 0 && <b> (live)</b>}
            </span>
            {i > 0 && (
              <button type="button" className="text-maroon-soft underline" onClick={() => restore(v.id)}>
                Restore
              </button>
            )}
          </li>
        ))}
        {versions.length === 0 && <li className="text-ink-soft">No saved versions yet.</li>}
      </ul>
    </details>
  );
}

function CmsTab() {
  const [hero, setHero] = useState({ headline: "", subheadline: "", cta_label: "" });
  const [story, setStory] = useState({ title: "", body: "" });
  const [error, setError] = useState("");
  const [savedKey, setSavedKey] = useState("");
  // Bumped on every save/restore so an open history list reloads.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api.get("/cms/home.hero", null).then((r) => setHero(r.content)).catch(() => {});
    api.get("/cms/brand.story", null).then((r) => setStory(r.content)).catch(() => {});
  }, []);

  async function save(key, content) {
    setError("");
    setSavedKey("");
    try {
      await api.put(`/cms/${key}`, { content });
      await revalidatePublicPages();
      setSavedKey(key);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err.message);
    }
  }
  function saveHero(e) {
    e.preventDefault();
    save("home.hero", hero);
  }
  function saveStory(e) {
    e.preventDefault();
    save("brand.story", story);
  }
  function restored(setter) {
    return (content) => {
      setter(content);
      setVersion((v) => v + 1);
    };
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-700">{error}</p>}
      <form onSubmit={saveHero} className="card p-5 flex flex-col gap-2">
        <h2 className="font-semibold">Homepage Hero</h2>
        <input className="input" value={hero.headline} onChange={(e) => setHero({ ...hero, headline: e.target.value })} placeholder="Headline" />
        <textarea className="input" value={hero.subheadline} onChange={(e) => setHero({ ...hero, subheadline: e.target.value })} placeholder="Subheadline" />
        <input className="input" value={hero.cta_label} onChange={(e) => setHero({ ...hero, cta_label: e.target.value })} placeholder="Button label" />
        <div className="flex items-center gap-3">
          <button className="btn-primary self-start">Save</button>
          {savedKey === "home.hero" && <span className="text-sm text-leaf">Saved — live now.</span>}
        </div>
        <CmsHistory cmsKey="home.hero" version={version} onRestored={restored(setHero)} />
      </form>
      <form onSubmit={saveStory} className="card p-5 flex flex-col gap-2">
        <h2 className="font-semibold">Brand Story</h2>
        <input className="input" value={story.title} onChange={(e) => setStory({ ...story, title: e.target.value })} placeholder="Title" />
        <textarea className="input" value={story.body} onChange={(e) => setStory({ ...story, body: e.target.value })} placeholder="Body" />
        <div className="flex items-center gap-3">
          <button className="btn-primary self-start">Save</button>
          {savedKey === "brand.story" && <span className="text-sm text-leaf">Saved — live now.</span>}
        </div>
        <CmsHistory cmsKey="brand.story" version={version} onRestored={restored(setStory)} />
      </form>
    </div>
  );
}
