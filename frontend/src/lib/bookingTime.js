export function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** Expected arrival and finish for a booking. Arrival is the scheduled
 * time, or now + live ETA once the artist is on the way (never earlier than
 * scheduled), or the actual check-in time once they've arrived; finish is
 * arrival + the package duration. `scheduled_at` is the consumer's local
 * time; `artist_arrived_at` is naive UTC from the server. */
export function serviceWindow(booking, now = Date.now()) {
  if (!booking.package_duration_minutes) return null;
  const scheduled = new Date(booking.scheduled_at);
  let arrival = scheduled;
  if (booking.artist_arrived_at) {
    arrival = new Date(booking.artist_arrived_at + "Z");
  } else if (booking.status === "artist_enroute" && booking.eta_minutes != null) {
    arrival = new Date(Math.max(now + booking.eta_minutes * 60000, scheduled.getTime()));
  }
  const finish = new Date(arrival.getTime() + booking.package_duration_minutes * 60000);
  return { arrival, finish };
}
