import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function CustomerDashboard() {
  const [me, setMe] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/users/me").then(setMe).catch((e) => setError(e.message));
    api.get("/users/me/dashboard").then(setDashboard).catch((e) => setError(e.message));
  }, []);

  const checklist = dashboard
    ? [
        { label: "Add your name", done: dashboard.profile_completion.has_name },
        { label: "Add your gender (for artist safety-matching)", done: dashboard.profile_completion.has_gender },
        { label: "Pick or upload an avatar", done: dashboard.profile_completion.has_avatar },
      ]
    : [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-4 flex-wrap">
        <img
          src={me?.avatar_url || "/avatars/preset-1.svg"}
          alt=""
          className="h-16 w-16 rounded-full object-cover border-2 border-gold"
        />
        <div>
          <h1 className="text-2xl">Namaste{me?.name ? `, ${me.name}` : ""}</h1>
          <p className="text-sm text-ink-soft">{me?.phone}</p>
        </div>
        <div className="flex gap-2 ml-auto flex-wrap">
          <Link href="/customer/favorites" className="btn-secondary text-sm">
            ♥ Favorites
          </Link>
          <Link href="/shop/orders" className="btn-secondary text-sm">
            🛍 My Orders
          </Link>
          <Link href="/customer/profile" className="btn-secondary text-sm">
            My Profile &amp; Avatar
          </Link>
        </div>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {dashboard && dashboard.profile_completion.percent < 100 && (
        <div className="invitation-frame p-5">
          <span className="corner-tl" aria-hidden="true" />
          <span className="corner-tr" aria-hidden="true" />
          <span className="corner-bl" aria-hidden="true" />
          <span className="corner-br" aria-hidden="true" />
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold">Complete your profile</h2>
            <span className="chip">{dashboard.profile_completion.percent}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-gold-soft overflow-hidden mb-3">
            <div className="h-full bg-gold" style={{ width: `${dashboard.profile_completion.percent}%` }} />
          </div>
          <ul className="flex flex-col gap-1 text-sm">
            {checklist.map((item) => (
              <li key={item.label} className={item.done ? "text-ink-soft line-through" : ""}>
                {item.done ? "✓" : "○"} {item.label}
              </li>
            ))}
          </ul>
          <Link href="/customer/profile" className="btn-primary text-sm inline-block mt-3">
            Finish setting up
          </Link>
        </div>
      )}

      {dashboard && (
        <div className="grid sm:grid-cols-3 gap-3">
          <StatCard label="Total Bookings" value={dashboard.total_bookings} />
          <StatCard label="Upcoming" value={dashboard.upcoming_bookings} accent="gold" />
          <StatCard label="Completed" value={dashboard.completed_bookings} accent="leaf" />
        </div>
      )}

      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Recent Bookings</h2>
          <Link href="/my-bookings" className="text-sm text-maroon-soft underline">
            View all
          </Link>
        </div>
        <div className="flex flex-col gap-2">
          {dashboard?.recent_bookings.map((b) => (
            <Link key={b.id} href={`/booking-detail/${b.id}`} className="flex justify-between items-center border-b border-line pb-2 text-sm">
              <span>
                {b.package_name} {b.artist_name ? `with ${b.artist_name}` : ""} — {new Date(b.scheduled_at).toLocaleDateString()}
              </span>
              <span className="chip">{b.status.replaceAll("_", " ")}</span>
            </Link>
          ))}
          {dashboard && dashboard.recent_bookings.length === 0 && (
            <p className="text-sm text-ink-soft">
              No bookings yet —{" "}
              <Link href="/discover" className="underline text-maroon-soft">
                find an artist
              </Link>{" "}
              to get started.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

const ACCENT_CLASSES = { maroon: "text-maroon-soft", leaf: "text-leaf", gold: "text-gold" };

function StatCard({ label, value, accent = "maroon" }) {
  return (
    <div className="card p-4 text-center">
      <div className={`text-2xl font-semibold ${ACCENT_CLASSES[accent] || ACCENT_CLASSES.maroon}`}>{value}</div>
      <div className="text-xs text-ink-soft mt-1">{label}</div>
    </div>
  );
}
