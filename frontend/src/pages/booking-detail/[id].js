import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { formatTime, serviceWindow } from "@/lib/bookingTime";
import { formatPriceRange } from "@/lib/designs";
import FileUpload from "@/components/FileUpload";
import ChatPanel from "@/components/ChatPanel";
import LiveMap from "@/components/LiveMap";

const LOCATION_PING_INTERVAL_MS = 15000;
const STATUS_POLL_INTERVAL_MS = 15000;
const TERMINAL_STATUSES = ["completed", "cancelled"];

const ADVANCE_LABELS = {
  pending: "Advance due",
  paid: "Advance paid ✓",
  refunded: "Advance refunded",
  forfeited: "Advance forfeited",
};

const STATUS_LABELS = {
  requested: "Requested",
  negotiating: "Negotiating Price",
  confirmed: "Confirmed",
  artist_enroute: "Artist En Route",
  arrived: "Artist Arrived",
  in_progress: "Mehndi In Progress",
  design_uploaded: "Design Uploaded — Awaiting Confirmation",
  completed: "Completed",
  disputed: "Disputed",
  cancelled: "Cancelled",
};

export default function BookingDetail() {
  const router = useRouter();
  const { id } = router.query;
  const { user } = useAuth();

  const [booking, setBooking] = useState(null);
  const [offers, setOffers] = useState([]);
  const [design, setDesign] = useState(null);
  const [artistProfile, setArtistProfile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offerAmount, setOfferAmount] = useState("");
  const [offerMessage, setOfferMessage] = useState("");
  const [acceptAmount, setAcceptAmount] = useState("");
  const [reportCategory, setReportCategory] = useState("misconduct");
  const [reportDesc, setReportDesc] = useState("");
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState("");

  const isConsumer = booking && user && booking.consumer_id === user.id;
  const isArtist = booking && user && booking.artist_id === user.id;

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const b = await api.get(`/bookings/${id}`);
      setBooking(b);
      const o = await api.get(`/bookings/${id}/offers`);
      setOffers(o);
      if (["design_uploaded", "completed", "disputed", "cancelled"].includes(b.status)) {
        try {
          setDesign(await api.get(`/bookings/${id}/design`));
        } catch {
          setDesign(null);
        }
      }
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!booking || ["requested", "negotiating"].includes(booking.status)) return;
    api
      .get(`/artists/${booking.artist_id}/public-profile`)
      .then(setArtistProfile)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booking?.artist_id, booking?.status]);

  // Both sides: keep the booking live until it's finished - status changes
  // made by the other party (accepted, en route, arrived, design uploaded,
  // paid, dispute resolved) and the artist's live location while en route
  // show up without a reload. Paused while the tab is hidden, and caught
  // up immediately when it's shown again.
  useEffect(() => {
    if (!booking || TERMINAL_STATUSES.includes(booking.status)) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, STATUS_POLL_INTERVAL_MS);
    function onVisible() {
      if (document.visibilityState === "visible") refresh();
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // Re-arm only when the status changes, not on every polled update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booking?.status, refresh]);

  // Artist side: while marked en route, share live location every 15s.
  useEffect(() => {
    if (!isArtist || !booking || booking.status !== "artist_enroute") return;
    if (!navigator.geolocation) return;

    function ping() {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          api.post(`/bookings/${id}/location`, { lat: pos.coords.latitude, lng: pos.coords.longitude }).catch(() => {});
        },
        () => {},
        { enableHighAccuracy: true, timeout: 10000 }
      );
    }
    ping();
    const timer = setInterval(ping, LOCATION_PING_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [isArtist, booking?.status, id]);

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function submitOffer(e) {
    e.preventDefault();
    act(async () => {
      await api.post(`/bookings/${id}/offers`, { amount: Number(offerAmount), message: offerMessage || null });
      setOfferAmount("");
      setOfferMessage("");
    });
  }

  function respondOffer(offerId, action) {
    act(() => api.post(`/bookings/${id}/offers/${offerId}/respond`, { action }));
  }

  function acceptDirectly(e) {
    e.preventDefault();
    act(() => api.post(`/bookings/${id}/accept`, { amount: Number(acceptAmount) }));
  }

  function withGeolocation(cb) {
    return () =>
      act(
        () =>
          new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
              (pos) => cb(pos.coords.latitude, pos.coords.longitude).then(resolve).catch(reject),
              () => reject(new Error("Location permission is needed for this step."))
            );
          })
      );
  }

  // Uploading the finished design doubles as the artist's check-out, so
  // the location is attached when the browser can provide it - but a
  // denied/unavailable location never blocks the upload.
  function uploadDesign(file) {
    act(async () => {
      const coords = await new Promise((resolve) => {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve(pos.coords),
          () => resolve(null),
          { enableHighAccuracy: true, timeout: 8000 }
        );
      });
      const qs = coords ? `?lat=${coords.latitude}&lng=${coords.longitude}` : "";
      await api.upload(`/bookings/${id}/design-upload${qs}`, file);
    });
  }

  function recordSettlement(mode) {
    act(() => api.post(`/bookings/${id}/settlement`, { mode }));
  }

  function confirmDesign(satisfied) {
    act(() => api.post(`/bookings/${id}/design-confirm`, { satisfied }));
  }

  async function pay() {
    setBusy(true);
    setError("");
    try {
      const order = await api.post(`/bookings/${id}/payment/order`, {});
      if (order.already_paid) {
        // The advance already covered everything due in-app.
        await refresh();
        return;
      }
      if (order.razorpay_key_id === "dev_mode_no_key") {
        await api.post(`/bookings/${id}/payment/verify`, {
          razorpay_order_id: order.razorpay_order_id,
          razorpay_payment_id: "dev_payment",
          razorpay_signature: "dev",
        });
        await refresh();
        return;
      }
      const rzp = new window.Razorpay({
        key: order.razorpay_key_id,
        amount: Math.round(order.amount * 100),
        currency: order.currency,
        name: "AryaVeda Mehndi",
        description: order.is_full_escrow ? "Mehndi booking" : "Platform fee",
        order_id: order.razorpay_order_id,
        handler: async (response) => {
          await api.post(`/bookings/${id}/payment/verify`, {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          refresh();
        },
      });
      rzp.open();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function payAdvance() {
    setBusy(true);
    setError("");
    try {
      const order = await api.post(`/bookings/${id}/advance/order`, {});
      if (order.razorpay_key_id === "dev_mode_no_key") {
        await api.post(`/bookings/${id}/advance/verify`, {
          razorpay_order_id: order.razorpay_order_id,
          razorpay_payment_id: "dev_payment",
          razorpay_signature: "dev",
        });
        await refresh();
        return;
      }
      const rzp = new window.Razorpay({
        key: order.razorpay_key_id,
        amount: Math.round(order.amount * 100),
        currency: order.currency,
        name: "AryaVeda Mehndi",
        description: "Booking deposit",
        order_id: order.razorpay_order_id,
        handler: async (response) => {
          await api.post(`/bookings/${id}/advance/verify`, {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          refresh();
        },
      });
      rzp.open();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function submitReport(e) {
    e.preventDefault();
    act(async () => {
      await api.post(`/bookings/${id}/report`, { category: reportCategory, description: reportDesc });
      setReportDesc("");
    });
  }

  function submitReview(e) {
    e.preventDefault();
    act(() => api.post(`/bookings/${id}/review`, { rating: Number(reviewRating), comment: reviewComment }));
  }

  if (error && !booking) return <p className="text-red-700">{error}</p>;
  if (!booking) return <p className="text-ink-soft">Loading booking…</p>;

  const window_ = !TERMINAL_STATUSES.includes(booking.status) ? serviceWindow(booking) : null;
  const split = booking.payment_breakdown;

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

      <div className="card p-5">
        <div className="flex justify-between items-center gap-2 flex-wrap">
          <h1 className="text-xl">Booking</h1>
          <div className="flex gap-2">
            {booking.advance_amount > 0 && (
              <span className={`chip ${booking.advance_status === "paid" ? "text-leaf" : booking.advance_status === "forfeited" ? "text-red-700" : ""}`}>
                {ADVANCE_LABELS[booking.advance_status] || booking.advance_status}
              </span>
            )}
            <span className="chip">{STATUS_LABELS[booking.status] || booking.status}</span>
          </div>
        </div>
        <p className="text-sm text-ink-soft mt-1">{booking.address_text}</p>
        <p className="text-sm text-ink-soft">Scheduled: {new Date(booking.scheduled_at).toLocaleString()}</p>
        {booking.eta_minutes != null && <p className="text-sm text-ink-soft">Estimated travel time: ~{Math.round(booking.eta_minutes)} min</p>}
        {window_ && (
          <p className="text-sm text-ink-soft">
            {booking.artist_arrived_at ? "Arrived" : "Expected arrival"} ~{formatTime(window_.arrival)} · Finishes around{" "}
            {formatTime(window_.finish)} ({booking.package_duration_minutes} min session)
          </p>
        )}
        {booking.agreed_price != null && (
          <div className="text-sm mt-2">
            <p className="font-semibold text-maroon-soft">
              Agreed price ₹{booking.agreed_price} + platform fee ₹{booking.platform_fee} = ₹{booking.total_amount} total
            </p>
            {split && (
              <ul className="text-ink-soft mt-1 list-disc pl-5">
                {split.advance_credit > 0 && <li>₹{split.advance_credit} advance already paid — credited below</li>}
                <li>
                  {split.full_escrow ? "Pay in the app" : "Platform fee to pay in the app"}: <b>₹{split.in_app_due}</b>
                </li>
                {!split.full_escrow && (
                  <li>
                    Pay the artist directly (UPI/cash): <b>₹{split.artist_direct_due}</b>
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
        {isArtist && booking.consumer_rating_count > 0 && (
          <p className="text-xs text-ink-soft mt-2">
            Customer rating from other artists: ★ {booking.consumer_rating_avg} ({booking.consumer_rating_count})
          </p>
        )}
        {isArtist && booking.consumer_rating_count === 0 && ["requested", "negotiating"].includes(booking.status) && (
          <p className="text-xs text-ink-soft mt-2">New customer — no ratings from other artists yet.</p>
        )}
        {booking.dispute_outcome && (
          <p className="text-sm mt-2 border-l-2 border-gold pl-2">
            Dispute {booking.dispute_outcome === "released" ? "resolved — booking released" : "resolved — booking cancelled"}
            {booking.dispute_notes && <span className="text-ink-soft"> · {booking.dispute_notes}</span>}
          </p>
        )}
        {booking.status === "disputed" && (
          <p className="text-sm mt-2 text-red-700">Our team is reviewing this booking. You&apos;ll be notified once it&apos;s resolved.</p>
        )}
      </div>

      {/* The same design card for consumer and artist, until the finished
          photo replaces it with the side-by-side verification below. */}
      {(isConsumer || isArtist) && !design && (booking.design_id || booking.reference_design_image_url) && (
        <div className="card p-4 flex gap-4 items-center">
          {booking.reference_design_image_url && (
            <img
              src={booking.reference_design_image_url}
              alt="Chosen design"
              className="h-24 w-24 rounded-lg object-cover border border-line flex-none"
            />
          )}
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-ink-soft">Chosen design</p>
            {booking.design_id ? (
              <Link href={`/designs/${booking.design_id}`} className="font-semibold text-maroon-soft underline">
                {booking.design_name}
              </Link>
            ) : (
              <p className="font-semibold">Reference photo</p>
            )}
            {booking.design_id && (
              <p className="text-sm">
                {formatPriceRange(booking.package_price_min, booking.package_price_max)} · ~{booking.package_duration_minutes} min
              </p>
            )}
            <p className="text-xs text-ink-soft mt-1">
              {isArtist
                ? "Recreate this design — your finished photo is checked against it before the customer pays."
                : "Your finished mehndi is checked against this design before you pay."}
            </p>
          </div>
        </div>
      )}

      {isConsumer && artistProfile && (
        <div className="card p-4 flex items-center gap-3">
          <img
            src={artistProfile.profile_photo_url || "/avatars/preset-1.svg"}
            alt=""
            className="h-14 w-14 rounded-full object-cover border-2 border-gold flex-none"
          />
          <div className="min-w-0">
            <p className="font-semibold">{artistProfile.name || "Your Mehndi Artist"}</p>
            <p className="text-xs text-ink-soft">
              {artistProfile.rating_count > 0 ? `★ ${artistProfile.rating_avg} (${artistProfile.rating_count} reviews)` : "New artist"}
            </p>
            {artistProfile.bio && <p className="text-xs text-ink-soft line-clamp-2 mt-0.5">{artistProfile.bio}</p>}
          </div>
        </div>
      )}

      {booking.status === "artist_enroute" && (isConsumer || isArtist) && (
        <div className="card p-4 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm">
              {isConsumer ? "Your artist is on the way" : "Sharing your live location"}
            </h2>
            {booking.eta_minutes != null && <span className="chip">~{Math.round(booking.eta_minutes)} min away</span>}
          </div>
          <LiveMap
            destLat={booking.location_lat}
            destLng={booking.location_lng}
            currentLat={booking.artist_current_lat}
            currentLng={booking.artist_current_lng}
          />
          {booking.artist_location_updated_at ? (
            <p className="text-[11px] text-ink-soft">
              Last updated {new Date(booking.artist_location_updated_at).toLocaleTimeString()}
            </p>
          ) : (
            <p className="text-[11px] text-ink-soft">Waiting for the first location update…</p>
          )}
        </div>
      )}

      {booking.masked_call_number && (
        <div className="card p-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Call {isConsumer ? "the artist" : "the consumer"}</p>
            <p className="text-xs text-ink-soft">Your real numbers stay private — this connects you without sharing them.</p>
          </div>
          <a href={`tel:${booking.masked_call_number}`} className="btn-primary text-sm whitespace-nowrap">
            📞 {booking.masked_call_number}
          </a>
        </div>
      )}

      {error && <p className="text-sm text-red-700">{error}</p>}

      {(isConsumer || isArtist) && booking.status !== "cancelled" && <ChatPanel bookingId={id} />}

      {isArtist && booking.status === "requested" && (
        <div className="card p-5">
          <h2 className="font-semibold mb-1">New Booking Request</h2>
          <p className="text-sm text-ink-soft mb-3">
            Happy to take this at the price the consumer expects? Confirm it outright below — or use Price Negotiation
            underneath if you&apos;d rather propose a different amount first.
          </p>
          <form onSubmit={acceptDirectly} className="flex gap-2">
            <input
              className="input"
              type="number"
              min={booking.package_price_min ?? undefined}
              max={booking.package_price_max ?? undefined}
              placeholder={`₹${booking.package_price_min}–${booking.package_price_max}`}
              value={acceptAmount}
              onChange={(e) => setAcceptAmount(e.target.value)}
              required
            />
            <button className="btn-primary whitespace-nowrap" disabled={busy}>
              Accept Booking
            </button>
          </form>
        </div>
      )}

      {["requested", "negotiating"].includes(booking.status) && booking.package_negotiable && (
        <div className="card p-5">
          <h2 className="font-semibold mb-1">Price Negotiation</h2>
          <p className="text-xs text-ink-soft mb-2">
            Offers must be within {formatPriceRange(booking.package_price_min, booking.package_price_max)} for this{" "}
            {booking.design_id ? "design" : "package"}.
          </p>
          <div className="flex flex-col gap-2 mb-3">
            {offers.map((o) => (
              <div key={o.id} className="flex justify-between items-center text-sm border-b border-line pb-2">
                <div>
                  <b>{o.proposed_by}</b> offered ₹{o.amount} {o.message && `— "${o.message}"`}
                  <div className="text-xs text-ink-soft">{o.status}</div>
                </div>
                {o.status === "pending" &&
                  ((isConsumer && o.proposed_by === "artist") || (isArtist && o.proposed_by === "consumer")) && (
                    <div className="flex gap-2">
                      <button className="btn-secondary text-xs" disabled={busy} onClick={() => respondOffer(o.id, "accept")}>
                        Accept
                      </button>
                      <button className="text-xs text-red-700" disabled={busy} onClick={() => respondOffer(o.id, "reject")}>
                        Reject
                      </button>
                    </div>
                  )}
              </div>
            ))}
            {offers.length === 0 && <p className="text-sm text-ink-soft">No offers yet.</p>}
          </div>
          <form onSubmit={submitOffer} className="flex gap-2">
            <input
              className="input"
              type="number"
              min={booking.package_price_min ?? undefined}
              max={booking.package_price_max ?? undefined}
              placeholder="Your offer (₹)"
              value={offerAmount}
              onChange={(e) => setOfferAmount(e.target.value)}
              required
            />
            <input className="input" placeholder="Message (optional)" value={offerMessage} onChange={(e) => setOfferMessage(e.target.value)} />
            <button className="btn-primary" disabled={busy}>
              Propose
            </button>
          </form>
        </div>
      )}

      {booking.status === "confirmed" && booking.advance_status === "pending" && (
        <div className="card p-5">
          <h2 className="font-semibold mb-1">Booking Deposit</h2>
          <p className="text-sm text-ink-soft mb-3">
            {isConsumer
              ? `Pay a ₹${booking.advance_amount} deposit to secure your slot — your artist won't head out until this is paid. Refundable if you cancel before they leave, not after.`
              : `Waiting on the consumer to pay a ₹${booking.advance_amount} deposit before you can mark yourself en route.`}
          </p>
          {isConsumer && (
            <button className="btn-primary" disabled={busy} onClick={payAdvance}>
              Pay ₹{booking.advance_amount} Deposit
            </button>
          )}
        </div>
      )}

      {isArtist && booking.status === "confirmed" && booking.advance_status !== "pending" && (
        <button className="btn-primary" disabled={busy} onClick={() => act(() => api.post(`/bookings/${id}/enroute`, {}))}>
          Mark En Route
        </button>
      )}
      {isArtist && booking.status === "artist_enroute" && (
        <button
          className="btn-primary"
          disabled={busy}
          onClick={withGeolocation((lat, lng) => api.post(`/bookings/${id}/arrived`, {}, { lat, lng }))}
        >
          Mark Arrived (shares your location)
        </button>
      )}
      {isArtist && booking.status === "arrived" && (
        <button className="btn-primary" disabled={busy} onClick={() => act(() => api.post(`/bookings/${id}/start`, {}))}>
          Start Mehndi
        </button>
      )}
      {isArtist && booking.status === "in_progress" && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">Upload Completed Design</h2>
          <FileUpload
            onFile={uploadDesign}
            busy={busy}
            label="Upload the finished mehndi photo"
            hint="Payment can't unlock for the consumer until this is uploaded."
          />
        </div>
      )}

      {isArtist && ["design_uploaded", "completed"].includes(booking.status) && !split?.full_escrow && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">How Were You Paid?</h2>
          <p className="text-sm text-ink-soft mb-2">
            Record how the consumer paid you the package amount (₹{split ? split.artist_direct_due : booking.agreed_price}) directly — this is
            separate from the platform fee.
            {split?.platform_owes_artist > 0 && ` The remaining ₹${split.platform_owes_artist} of their advance is paid out to you by AryaVeda.`}
          </p>
          {booking.settlement_mode ? (
            <p className="text-sm">
              Recorded: <b>{booking.settlement_mode.replaceAll("_", " ")}</b>
            </p>
          ) : (
            <div className="flex gap-2 flex-wrap">
              {["upi", "cash", "bank_transfer", "other"].map((mode) => (
                <button key={mode} className="btn-secondary text-xs" disabled={busy} onClick={() => recordSettlement(mode)}>
                  {mode.replaceAll("_", " ")}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {design && (
        <div className="card p-5">
          <h2 className="font-semibold mb-2">Design Verification</h2>
          <div className={`grid gap-3 mb-2 ${design.reference_image_url ? "grid-cols-2" : "grid-cols-1"}`}>
            {design.reference_image_url && (
              <figure className="flex flex-col gap-1">
                <img src={design.reference_image_url} alt="Chosen design" className="rounded-lg w-full aspect-square object-cover border border-line" />
                <figcaption className="text-xs text-ink-soft text-center">Chosen{booking.design_name ? `: ${booking.design_name}` : ""}</figcaption>
              </figure>
            )}
            <figure className="flex flex-col gap-1">
              <img
                src={design.completed_image_url}
                alt="Completed design"
                className={`rounded-lg w-full object-cover border border-line ${design.reference_image_url ? "aspect-square" : "max-h-64"}`}
              />
              <figcaption className="text-xs text-ink-soft text-center">Finished</figcaption>
            </figure>
          </div>
          {design.similarity_score != null && <p className="text-sm">Match score: {design.similarity_score}%</p>}
          <p className="text-sm mb-2">Status: {design.match_status.replaceAll("_", " ")}</p>

          {isConsumer && design.match_status === "needs_consumer_confirmation" && (
            <div className="flex gap-2">
              <button className="btn-primary" disabled={busy} onClick={() => confirmDesign(true)}>
                Yes, I&apos;m satisfied
              </button>
              <button className="text-red-700 text-sm" disabled={busy} onClick={() => confirmDesign(false)}>
                No, raise a dispute
              </button>
            </div>
          )}

          {isConsumer && ["auto_matched", "consumer_confirmed"].includes(design.match_status) && booking.status === "design_uploaded" && (
            <button className="btn-primary mt-2" disabled={busy} onClick={pay}>
              {split && split.in_app_due <= 0
                ? "Complete Booking (covered by your advance)"
                : `Pay ${split?.full_escrow ? "" : "Platform Fee "}(₹${split ? split.in_app_due : booking.platform_fee})`}
            </button>
          )}
        </div>
      )}

      {booking.status !== "requested" && (
        <details className="card p-5">
          <summary className="font-semibold cursor-pointer">Report a Problem</summary>
          <p className="text-xs text-ink-soft mt-2">
            {["arrived", "in_progress", "design_uploaded"].includes(booking.status)
              ? "Reporting now pauses this booking (and payment) until our team reviews it."
              : "Our team will review your report."}
          </p>
          <form onSubmit={submitReport} className="flex flex-col gap-2 mt-3">
            <select className="input" value={reportCategory} onChange={(e) => setReportCategory(e.target.value)}>
              <option value="misconduct">Misconduct</option>
              <option value="no_show">No-show</option>
              <option value="poor_quality">Poor quality</option>
              <option value="safety">Safety concern</option>
              <option value="other">Other</option>
            </select>
            <textarea className="input" placeholder="Describe what happened" value={reportDesc} onChange={(e) => setReportDesc(e.target.value)} />
            <button className="btn-secondary" disabled={busy}>
              Submit Report
            </button>
          </form>
        </details>
      )}

      {["completed", "disputed"].includes(booking.status) && (
        <form onSubmit={submitReview} className="card p-5 flex flex-col gap-2">
          <h2 className="font-semibold">Leave a Review</h2>
          <select className="input" value={reviewRating} onChange={(e) => setReviewRating(e.target.value)}>
            {[5, 4, 3, 2, 1].map((n) => (
              <option key={n} value={n}>
                {n} stars
              </option>
            ))}
          </select>
          <textarea className="input" placeholder="How did it go?" value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} />
          <button className="btn-primary" disabled={busy}>
            Submit Review
          </button>
        </form>
      )}

      {["requested", "negotiating", "confirmed", "artist_enroute", "arrived"].includes(booking.status) && (
        <div className="flex flex-col gap-1 items-start">
          {booking.advance_status === "paid" && ["artist_enroute", "arrived"].includes(booking.status) && (
            <p className="text-xs text-red-700">
              Your artist is already on the way — cancelling now forfeits the ₹{booking.advance_amount} deposit.
            </p>
          )}
          <button
            className="text-sm text-red-700"
            disabled={busy}
            onClick={() => {
              const warn =
                booking.advance_status === "paid" && ["artist_enroute", "arrived"].includes(booking.status)
                  ? `Cancelling now will forfeit your ₹${booking.advance_amount} deposit since the artist has already left. Cancel anyway?`
                  : null;
              if (warn && !window.confirm(warn)) return;
              act(() => api.post(`/bookings/${id}/cancel`, {}));
            }}
          >
            Cancel Booking
          </button>
        </div>
      )}
    </div>
  );
}
