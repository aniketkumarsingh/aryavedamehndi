import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

const SETTLEMENT_LABELS = { upi: "UPI", cash: "Cash", bank_transfer: "Bank Transfer", other: "Other" };
const TXN_PAGE_SIZE = 20;

export default function ArtistDashboard() {
  const [profile, setProfile] = useState(null);
  const [profileMissing, setProfileMissing] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [slots, setSlots] = useState([]);
  const [slotDate, setSlotDate] = useState("");
  const [slotStart, setSlotStart] = useState("10:00");
  const [slotEnd, setSlotEnd] = useState("11:00");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [txnHasMore, setTxnHasMore] = useState(false);
  const [txnLoadingMore, setTxnLoadingMore] = useState(false);

  function load() {
    api
      .get("/artists/me/profile")
      .then((p) => {
        setProfile(p);
        setProfileMissing(false);
      })
      .catch(() => setProfileMissing(true));
    api.get("/artists/me/dashboard").then(setDashboard).catch(() => {});
    api
      .get("/artists/me/transactions", { limit: TXN_PAGE_SIZE, offset: 0 })
      .then((rows) => {
        setTransactions(rows);
        setTxnHasMore(rows.length === TXN_PAGE_SIZE);
      })
      .catch(() => {});
    api.get("/bookings").then(setBookings).catch(() => {});
  }

  useEffect(load, []);

  async function loadMoreTransactions() {
    setTxnLoadingMore(true);
    try {
      const rows = await api.get("/artists/me/transactions", { limit: TXN_PAGE_SIZE, offset: transactions.length });
      setTransactions((prev) => [...prev, ...rows]);
      setTxnHasMore(rows.length === TXN_PAGE_SIZE);
    } catch (err) {
      setError(err.message);
    } finally {
      setTxnLoadingMore(false);
    }
  }

  useEffect(() => {
    if (profile) {
      api
        .get(`/artists/${profile.user_id}/availability`, { from_date: new Date().toISOString().slice(0, 10) })
        .then(setSlots)
        .catch(() => {});
    }
  }, [profile]);

  async function addSlot(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/artists/me/availability", { slot_date: slotDate, start_time: slotStart, end_time: slotEnd });
      const updated = await api.get(`/artists/${profile.user_id}/availability`, { from_date: new Date().toISOString().slice(0, 10) });
      setSlots(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl">Artist Dashboard</h1>
        <Link href="/artist/profile" className="btn-secondary text-sm">
          My Profile &amp; Verification
        </Link>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {profileMissing && (
        <div className="card p-5">
          <p className="text-sm">
            Set up your profile before you can receive bookings —{" "}
            <Link href="/artist/profile" className="underline text-maroon-soft">
              go to My Profile
            </Link>
            .
          </p>
        </div>
      )}

      {profile && (
        <p className="text-sm text-ink-soft">
          KYC status: <b>{profile.kyc_status}</b>
          {profile.kyc_status !== "approved" && " — an admin needs to approve your documents before you appear in search."}
        </p>
      )}

      {dashboard && (
        <>
          <div className="grid sm:grid-cols-3 gap-3">
            <StatCard label="Total Orders" value={dashboard.orders_taken} />
            <StatCard label="Orders Completed" value={dashboard.orders_completed} accent="leaf" />
            <StatCard label="Orders Missed" value={dashboard.orders_missed} accent="maroon" />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <StatCard label="Rating" value={dashboard.rating_count ? `${dashboard.rating_avg} ★ (${dashboard.rating_count})` : "New"} />
            <StatCard label="Total Earnings" value={`₹${dashboard.total_earnings}`} />
          </div>

          <div className="card p-5">
            <h2 className="font-semibold mb-2">How You Were Paid</h2>
            {dashboard.settlement_breakdown.length === 0 && (
              <p className="text-sm text-ink-soft">Nothing recorded yet — mark how you were paid from a booking&apos;s page after finishing the service.</p>
            )}
            <div className="flex flex-col gap-1">
              {dashboard.settlement_breakdown.map((s) => (
                <div key={s.mode} className="flex justify-between text-sm border-b border-line pb-1">
                  <span>{SETTLEMENT_LABELS[s.mode] || s.mode}</span>
                  <span>
                    {s.count} order{s.count !== 1 ? "s" : ""} · ₹{s.total_amount}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Transaction History</h2>
        {transactions.length === 0 && <p className="text-sm text-ink-soft">No transactions yet.</p>}
        {transactions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-soft uppercase tracking-wide">
                  <th className="pb-2 pr-3">Date</th>
                  <th className="pb-2 pr-3">Package</th>
                  <th className="pb-2 pr-3">Amount</th>
                  <th className="pb-2 pr-3">Platform Fee</th>
                  <th className="pb-2 pr-3">Paid Via</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-t border-line">
                    <td className="py-2 pr-3">{new Date(t.scheduled_at).toLocaleDateString()}</td>
                    <td className="py-2 pr-3">{t.package_name}</td>
                    <td className="py-2 pr-3">{t.agreed_price != null ? `₹${t.agreed_price}` : "—"}</td>
                    <td className="py-2 pr-3">{t.platform_fee != null ? `₹${t.platform_fee}` : "—"}</td>
                    <td className="py-2 pr-3">{t.settlement_mode ? SETTLEMENT_LABELS[t.settlement_mode] || t.settlement_mode : "—"}</td>
                    <td className="py-2">
                      <span className="chip">{t.status.replaceAll("_", " ")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {txnHasMore && (
          <button className="btn-secondary text-sm mt-3" onClick={loadMoreTransactions} disabled={txnLoadingMore}>
            {txnLoadingMore ? "Loading…" : "Load more"}
          </button>
        )}
      </div>

      {profile && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">Availability Slots</h2>
          <form onSubmit={addSlot} className="flex gap-2 flex-wrap mb-3">
            <input className="input w-auto" type="date" value={slotDate} onChange={(e) => setSlotDate(e.target.value)} required />
            <input className="input w-auto" type="time" value={slotStart} onChange={(e) => setSlotStart(e.target.value)} required />
            <input className="input w-auto" type="time" value={slotEnd} onChange={(e) => setSlotEnd(e.target.value)} required />
            <button className="btn-secondary" disabled={busy}>
              Add Slot
            </button>
          </form>
          <div className="flex flex-wrap gap-2 text-sm">
            {slots.map((s) => (
              <span key={s.id} className="chip">
                {s.slot_date} {s.start_time}–{s.end_time}
              </span>
            ))}
            {slots.length === 0 && <p className="text-ink-soft">No open slots yet.</p>}
          </div>
        </div>
      )}

      <div className="card p-5">
        <h2 className="font-semibold mb-2">Bookings</h2>
        <div className="flex flex-col gap-2">
          {bookings.map((b) => (
            <Link key={b.id} href={`/booking-detail/${b.id}`} className="flex justify-between items-center border-b border-line pb-2 text-sm">
              <span>{new Date(b.scheduled_at).toLocaleString()}</span>
              <span className="chip">{b.status.replaceAll("_", " ")}</span>
            </Link>
          ))}
          {bookings.length === 0 && <p className="text-sm text-ink-soft">No bookings yet.</p>}
        </div>
      </div>
    </div>
  );
}

const ACCENT_CLASSES = {
  maroon: "text-maroon-soft",
  leaf: "text-leaf",
  gold: "text-gold",
};

function StatCard({ label, value, accent = "gold" }) {
  return (
    <div className="card p-4 text-center">
      <div className={`text-2xl font-semibold ${ACCENT_CLASSES[accent] || ACCENT_CLASSES.gold}`}>{value}</div>
      <div className="text-xs text-ink-soft mt-1">{label}</div>
    </div>
  );
}
