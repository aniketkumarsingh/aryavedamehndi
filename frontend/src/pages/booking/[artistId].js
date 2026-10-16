import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { api } from "@/lib/api";

export default function NewBooking() {
  const router = useRouter();
  const { artistId, package_id: rebookPackageId } = router.query;

  const [packages, setPackages] = useState([]);
  const [packageId, setPackageId] = useState("");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState(null);
  const [slots, setSlots] = useState([]);
  const [selectedSlotId, setSelectedSlotId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [genderPref, setGenderPref] = useState("same");
  const [openingOffer, setOpeningOffer] = useState("");
  const [referenceImage, setReferenceImage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/packages").then(setPackages).catch(() => {});
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => setError("Allow location access so we can calculate your artist's ETA.")
      );
    }
  }, []);

  useEffect(() => {
    if (rebookPackageId) setPackageId(String(rebookPackageId));
  }, [rebookPackageId]);

  useEffect(() => {
    if (!artistId) return;
    api
      .get(`/artists/${artistId}/availability`, { from_date: new Date().toISOString().slice(0, 10) })
      .then(setSlots)
      .catch(() => {});
  }, [artistId]);

  const selectedPackage = packages.find((p) => p.id === packageId);
  const selectedSlot = slots.find((s) => s.id === selectedSlotId);

  function pickSlot(slot) {
    setSelectedSlotId(slot.id);
    setScheduledAt(`${slot.slot_date}T${slot.start_time.slice(0, 5)}`);
  }

  async function submit(e) {
    e.preventDefault();
    if (!coords) {
      setError("Location is required to book.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const booking = await api.post("/bookings", {
        artist_id: artistId,
        package_id: packageId,
        address_text: address,
        location_lat: coords.lat,
        location_lng: coords.lng,
        scheduled_at: new Date(scheduledAt).toISOString(),
        gender_preference: genderPref,
        reference_design_image_url: referenceImage || null,
        opening_offer: openingOffer ? Number(openingOffer) : null,
        availability_slot_id: selectedSlot ? selectedSlot.id : null,
      });
      router.push(`/booking-detail/${booking.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto card p-6">
      <h1 className="text-xl mb-4">Book This Artist</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="text-sm font-semibold">Package</label>
        <select className="input" value={packageId} onChange={(e) => setPackageId(e.target.value)} required>
          <option value="">Select a package</option>
          {packages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} (₹{p.price_min}–₹{p.price_max})
            </option>
          ))}
        </select>

        {selectedPackage?.advance_amount > 0 && (
          <p className="text-xs bg-gold-soft rounded-lg px-3 py-2">
            This package needs a ₹{selectedPackage.advance_amount} booking deposit once your artist confirms the price — it
            secures your slot and is refundable if you cancel before the artist heads out, but not after.
          </p>
        )}

        {selectedPackage?.sample_image_urls && (
          <div>
            <label className="text-sm font-semibold">Reference design (optional)</label>
            <div className="flex gap-2 mt-1 flex-wrap">
              {selectedPackage.sample_image_urls.split(",").map((url) => (
                <img
                  key={url}
                  src={url}
                  alt="sample design"
                  onClick={() => setReferenceImage(url)}
                  className={`w-16 h-16 object-cover rounded-lg cursor-pointer border-2 ${
                    referenceImage === url ? "border-maroon" : "border-transparent"
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-ink-soft mt-1">
              Picking one lets us auto-verify the finished design matches what you asked for.
            </p>
          </div>
        )}

        <label className="text-sm font-semibold">Address</label>
        <input className="input" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Where should the artist come?" required />

        {slots.length > 0 ? (
          <div>
            <label className="text-sm font-semibold">Pick an open slot</label>
            <div className="flex gap-2 flex-wrap mt-1">
              {slots.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => pickSlot(s)}
                  className={`rounded-full border-2 px-3 py-1.5 text-xs font-semibold transition-colors ${
                    selectedSlotId === s.id ? "border-maroon bg-gold-soft text-maroon" : "border-line text-ink-soft"
                  }`}
                >
                  {new Date(s.slot_date).toLocaleDateString(undefined, { day: "numeric", month: "short" })} ·{" "}
                  {s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="text-xs text-ink-soft underline mt-1"
              onClick={() => {
                setSelectedSlotId("");
                setScheduledAt("");
              }}
            >
              None of these work — pick my own date/time instead
            </button>
            {!selectedSlotId && (
              <input
                className="input mt-2"
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                required
              />
            )}
          </div>
        ) : (
          <>
            <label className="text-sm font-semibold">Date &amp; time</label>
            <input className="input" type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} required />
          </>
        )}

        <label className="text-sm font-semibold">Artist gender preference</label>
        <select className="input" value={genderPref} onChange={(e) => setGenderPref(e.target.value)}>
          <option value="same">Same as mine (recommended)</option>
          <option value="any">No preference</option>
        </select>

        {selectedPackage?.negotiable && (
          <>
            <label className="text-sm font-semibold">
              Your opening price offer (optional, band: ₹{selectedPackage.price_min}–₹{selectedPackage.price_max})
            </label>
            <input
              className="input"
              type="number"
              value={openingOffer}
              onChange={(e) => setOpeningOffer(e.target.value)}
              placeholder="Leave blank to accept the listed price"
            />
          </>
        )}

        {error && <p className="text-sm text-red-700">{error}</p>}

        <button className="btn-primary mt-2" disabled={loading}>
          {loading ? "Booking..." : "Request Booking"}
        </button>
      </form>
    </div>
  );
}
