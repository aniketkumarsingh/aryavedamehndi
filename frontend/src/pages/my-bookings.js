import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { api } from "@/lib/api";
import BookingCalendar from "@/components/BookingCalendar";
import { BULK_STATUS_LABELS, bulkOccasionLabel } from "@/lib/pricing";

export default function MyBookings() {
  const router = useRouter();
  const [bookings, setBookings] = useState([]);
  const [eventOrders, setEventOrders] = useState([]);
  const [error, setError] = useState("");
  const [view, setView] = useState("list");
  const [selectedDay, setSelectedDay] = useState(null);
  const [dayBookings, setDayBookings] = useState([]);

  useEffect(() => {
    api.get("/bookings").then(setBookings).catch((e) => setError(e.message));
    api.get("/bulk-orders").then(setEventOrders).catch(() => {});
  }, []);

  function rebook(b) {
    router.push(`/booking/${b.artist_id}?package_id=${b.package_id}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl">My Bookings</h1>
        <div className="flex gap-2">
          <button className={view === "list" ? "btn-primary text-sm" : "btn-secondary text-sm"} onClick={() => setView("list")}>
            List
          </button>
          <button className={view === "calendar" ? "btn-primary text-sm" : "btn-secondary text-sm"} onClick={() => setView("calendar")}>
            Calendar
          </button>
        </div>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {view === "calendar" && (
        <>
          <BookingCalendar
            bookings={bookings}
            onSelectDay={(dayItems, d) => {
              setDayBookings(dayItems);
              setSelectedDay(d);
            }}
          />
          {selectedDay && (
            <div className="card p-5">
              <h2 className="font-semibold mb-2">{selectedDay.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</h2>
              {dayBookings.length === 0 && <p className="text-sm text-ink-soft">No bookings on this day.</p>}
              <div className="flex flex-col gap-2">
                {dayBookings.map((b) => (
                  <BookingRow key={b.id} b={b} onRebook={rebook} />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {view === "list" && eventOrders.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="font-semibold">Event orders</h2>
          {eventOrders.map((o) => (
            <Link key={o.id} href={`/bulk-orders/${o.id}`} className="card p-4 flex justify-between items-center gap-3">
              <div className="min-w-0">
                <p className="font-semibold truncate">
                  {bulkOccasionLabel(o.occasion)} · {o.people} people
                </p>
                <p className="text-sm text-ink-soft">{new Date(o.event_at + "Z").toLocaleString()}</p>
              </div>
              <span className="chip flex-none">{BULK_STATUS_LABELS[o.status] || o.status}</span>
            </Link>
          ))}
          <h2 className="font-semibold mt-2">Bookings</h2>
        </div>
      )}

      {view === "list" && (
        <div className="flex flex-col gap-3">
          {bookings.map((b) => (
            <BookingRow key={b.id} b={b} onRebook={rebook} card />
          ))}
          {bookings.length === 0 && (
            <p className="text-sm text-ink-soft">
              No bookings yet — go find an artist, or{" "}
              <Link href="/custom-order" className="text-maroon-soft underline">
                place a custom or event order
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function BookingRow({ b, onRebook, card }) {
  const canRebook = ["completed", "cancelled"].includes(b.status);
  return (
    <div className={`flex justify-between items-center gap-3 ${card ? "card p-4" : "border-b border-line pb-2"}`}>
      <Link href={`/booking-detail/${b.id}`} className="flex-1 min-w-0">
        <p className="font-semibold truncate">{b.address_text || "Booking"}</p>
        <p className="text-sm text-ink-soft">{new Date(b.scheduled_at).toLocaleString()}</p>
      </Link>
      <div className="flex items-center gap-2 flex-none">
        <span className="chip">{b.status.replaceAll("_", " ")}</span>
        {canRebook && (
          <button className="btn-secondary text-xs" onClick={() => onRebook(b)}>
            Rebook
          </button>
        )}
      </div>
    </div>
  );
}
