import { useEffect, useState } from "react";
import Stars from "@/components/Stars";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useLanguage } from "@/lib/useLanguage";

const MAX_PHOTOS = 3;

function ReviewForm({ productId, existing, onSaved }) {
  const { t } = useLanguage();
  const [rating, setRating] = useState(existing?.rating || 0);
  const [title, setTitle] = useState(existing?.title || "");
  const [body, setBody] = useState(existing?.body || "");
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!rating) return setError(t("review_pick_rating"));
    const form = new FormData();
    form.append("rating", String(rating));
    if (title.trim()) form.append("title", title.trim());
    if (body.trim()) form.append("body", body.trim());
    for (const p of photos) form.append("photos", p);
    setBusy(true);
    setError("");
    try {
      await api.uploadForm(`/shop/products/${productId}/reviews`, form);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 flex flex-col gap-2 text-sm">
      <h3 className="font-semibold">{existing ? t("review_edit") : t("review_write")}</h3>
      <div className="flex gap-1" role="radiogroup" aria-label={t("review_rating")}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={rating === n}
            aria-label={`${n}`}
            onClick={() => setRating(n)}
            className={`text-2xl leading-none ${n <= rating ? "text-gold" : "text-line"}`}
          >
            ★
          </button>
        ))}
      </div>
      <input className="input" maxLength={120} placeholder={t("review_title_placeholder")} value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea className="input" maxLength={3000} placeholder={t("review_body_placeholder")} value={body} onChange={(e) => setBody(e.target.value)} />
      <label className="text-xs text-ink-soft">
        {t("review_photos", { max: MAX_PHOTOS })}
        <input type="file" accept="image/*" multiple className="block mt-1" onChange={(e) => setPhotos([...e.target.files].slice(0, MAX_PHOTOS))} />
      </label>
      {error && <p className="text-red-700">{error}</p>}
      <button className="btn-primary self-start text-sm" disabled={busy}>{busy ? t("order_please_wait") : t("review_submit")}</button>
    </form>
  );
}

/** Verified-buyer reviews under a product: summary, list, and a form for
 * customers whose order with this product has been delivered. */
export default function ProductReviews({ product }) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [mine, setMine] = useState(null);
  const [editing, setEditing] = useState(false);

  function load() {
    api.get(`/shop/products/${product.id}/reviews`, { limit: 20 }).then(setData).catch(() => {});
    if (user?.role === "consumer") api.get(`/shop/products/${product.id}/reviews/mine`).then(setMine).catch(() => {});
  }
  useEffect(load, [product.id, user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return null;
  return (
    <section className="flex flex-col gap-3" aria-labelledby="reviews-heading">
      <h2 id="reviews-heading" className="text-xl">{t("review_heading")}</h2>
      {data.rating_count > 0 ? (
        <div className="flex flex-wrap items-center gap-4">
          <Stars value={data.rating_avg} count={data.rating_count} className="text-lg" />
          <div className="flex flex-col text-xs text-ink-soft">
            {Object.entries(data.breakdown).sort(([a], [b]) => b - a).map(([stars, n]) => (
              <span key={stars}>{stars}★ · {n}</span>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-sm text-ink-soft">{t("review_none")}</p>
      )}

      {mine?.can_review && (editing || !mine.review) && (
        <ReviewForm productId={product.id} existing={mine.review} onSaved={() => { setEditing(false); load(); }} />
      )}
      {mine?.can_review && mine.review && !editing && (
        <button className="text-xs underline self-start" onClick={() => setEditing(true)}>{t("review_edit")}</button>
      )}

      <div className="flex flex-col gap-3">
        {data.reviews.map((r) => (
          <article key={r.id} className="card p-4 flex flex-col gap-1 text-sm">
            <div className="flex justify-between gap-2 flex-wrap">
              <Stars value={r.rating} />
              <span className="text-xs text-ink-soft">
                {r.author} · {t("review_verified")} · {new Date(r.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
              </span>
            </div>
            {r.title && <p className="font-semibold">{r.title}</p>}
            {r.body && <p className="text-ink-soft whitespace-pre-line">{r.body}</p>}
            {r.photo_urls && (
              <div className="flex gap-2 flex-wrap">
                {r.photo_urls.split(",").map((url) => (
                  <a key={url} href={url} target="_blank" rel="noopener noreferrer">
                    <img src={url} alt="" className="h-20 w-20 object-cover rounded-lg border border-line" loading="lazy" />
                  </a>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
