import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const TABS = ["Overview", "Bookings", "Users", "Artists", "Packages", "KYC Approvals", "Reports", "Shop Products", "Shop Orders", "Brand Content"];

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
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  function load() {
    api
      .get("/admin/bookings", { status_filter: statusFilter, limit: PAGE_SIZE, offset: 0 })
      .then((rows) => {
        setBookings(rows);
        setHasMore(rows.length === PAGE_SIZE);
      })
      .catch((e) => setError(e.message));
  }
  useEffect(load, [statusFilter]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const rows = await api.get("/admin/bookings", { status_filter: statusFilter, limit: PAGE_SIZE, offset: bookings.length });
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
        <select className="input w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {["all", "requested", "negotiating", "confirmed", "artist_enroute", "arrived", "in_progress", "design_uploaded", "completed", "disputed", "cancelled"].map((s) => (
            <option key={s} value={s}>
              {s.replaceAll("_", " ")}
            </option>
          ))}
        </select>
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
          <option value="regular">Regular</option>
          <option value="bridal">Bridal</option>
          <option value="party">Party</option>
          <option value="festival">Festival</option>
          <option value="feet">Feet-only</option>
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
    api.get("/shop/products").then(setProducts).catch((e) => setError(e.message));
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
      <h2 className="font-semibold mb-3">Shop Products</h2>
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
  const images = (product.image_urls || "").split(",").filter(Boolean);

  async function uploadPhoto(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api.upload(`/shop/products/${product.id}/image`, file);
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
      await api.del(`/shop/products/${product.id}/image?url=${encodeURIComponent(url)}`);
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
          <b>{product.name}</b> — ₹{product.price}, {product.stock_quantity} in stock
          {!product.is_active && <span className="chip ml-2 text-red-700">inactive</span>}
        </div>
        <div className="flex gap-2">
          <label className="btn-secondary text-xs cursor-pointer">
            {busy ? "Uploading..." : "Upload photo"}
            <input type="file" accept="image/*" onChange={uploadPhoto} disabled={busy} className="hidden" />
          </label>
          {product.is_active && (
            <button className="text-xs text-red-700" onClick={onDeactivate}>
              Deactivate
            </button>
          )}
        </div>
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
                  {o.items.map((i) => `${i.product_name} ×${i.quantity}`).join(", ")}
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

function CmsTab() {
  const [hero, setHero] = useState({ headline: "", subheadline: "", cta_label: "" });
  const [story, setStory] = useState({ title: "", body: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/cms/home.hero", null).then((r) => setHero(r.content)).catch(() => {});
    api.get("/cms/brand.story", null).then((r) => setStory(r.content)).catch(() => {});
  }, []);

  async function saveHero(e) {
    e.preventDefault();
    try {
      await api.put("/cms/home.hero", { content: hero });
    } catch (err) {
      setError(err.message);
    }
  }
  async function saveStory(e) {
    e.preventDefault();
    try {
      await api.put("/cms/brand.story", { content: story });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-700">{error}</p>}
      <form onSubmit={saveHero} className="card p-5 flex flex-col gap-2">
        <h2 className="font-semibold">Homepage Hero</h2>
        <input className="input" value={hero.headline} onChange={(e) => setHero({ ...hero, headline: e.target.value })} placeholder="Headline" />
        <textarea className="input" value={hero.subheadline} onChange={(e) => setHero({ ...hero, subheadline: e.target.value })} placeholder="Subheadline" />
        <input className="input" value={hero.cta_label} onChange={(e) => setHero({ ...hero, cta_label: e.target.value })} placeholder="Button label" />
        <button className="btn-primary self-start">Save</button>
      </form>
      <form onSubmit={saveStory} className="card p-5 flex flex-col gap-2">
        <h2 className="font-semibold">Brand Story</h2>
        <input className="input" value={story.title} onChange={(e) => setStory({ ...story, title: e.target.value })} placeholder="Title" />
        <textarea className="input" value={story.body} onChange={(e) => setStory({ ...story, body: e.target.value })} placeholder="Body" />
        <button className="btn-primary self-start">Save</button>
      </form>
    </div>
  );
}
