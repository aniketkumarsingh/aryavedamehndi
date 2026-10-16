import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import Lightbox from "@/components/Lightbox";

const SEARCH_RADIUS_KM = 10;

export default function Discover() {
  const { user } = useAuth();
  const [coords, setCoords] = useState(null);
  const [genderFilter, setGenderFilter] = useState("");
  const [artists, setArtists] = useState([]);
  const [favoriteIds, setFavoriteIds] = useState(new Set());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lightbox, setLightbox] = useState(null); // { images, index }

  useEffect(() => {
    if (user?.role === "consumer") {
      api
        .get("/favorites")
        .then((favs) => setFavoriteIds(new Set(favs.map((f) => f.artist_id))))
        .catch(() => {});
    }
  }, [user]);

  async function toggleFavorite(artistId) {
    const isFav = favoriteIds.has(artistId);
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      isFav ? next.delete(artistId) : next.add(artistId);
      return next;
    });
    try {
      if (isFav) await api.del(`/favorites/${artistId}`);
      else await api.post(`/favorites/${artistId}`, {});
    } catch {
      /* revert isn't critical - next load will resync */
    }
  }

  useEffect(() => {
    if (!navigator.geolocation) {
      setError("Location isn't available in this browser — enter your area manually later.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setError("Location permission denied — allow location access to find nearby artists.")
    );
  }, []);

  useEffect(() => {
    if (!coords) return;
    setLoading(true);
    const query = { lat: coords.lat, lng: coords.lng, radius_km: SEARCH_RADIUS_KM };
    if (genderFilter) query.gender = genderFilter;
    api
      .get("/artists/nearby", query)
      .then(setArtists)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [coords, genderFilter]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl">Top-Rated Artists Near You</h1>
          <p className="text-sm text-ink-soft">Within {SEARCH_RADIUS_KM} km, sorted by rating.</p>
        </div>
        <div className="flex gap-2">
          {user?.role === "consumer" && (
            <Link href="/customer/favorites" className="btn-secondary text-sm">
              ♥ My Favorites
            </Link>
          )}
          <select className="input w-auto" value={genderFilter} onChange={(e) => setGenderFilter(e.target.value)}>
            <option value="">Any artist gender</option>
            <option value="female">Female artists only</option>
            <option value="male">Male artists only</option>
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-ink-soft">Finding artists near you...</p>}
      {!coords && !error && <p className="text-sm text-ink-soft">Waiting for your location…</p>}

      <div className="grid sm:grid-cols-2 gap-4">
        {artists.map((a) => (
          <div key={a.user_id} className="card overflow-hidden flex gap-4 p-4">
            <img
              src={a.profile_photo_url || "/avatars/preset-1.svg"}
              alt=""
              className="h-20 w-20 rounded-2xl object-cover border border-line flex-none"
            />
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <div className="flex justify-between items-start gap-2">
                <h3 className="font-semibold truncate">{a.name || "Mehndi Artist"}</h3>
                <div className="flex items-center gap-1 flex-none">
                  <span className="chip">{a.gender}</span>
                  {user?.role === "consumer" && (
                    <button
                      type="button"
                      onClick={() => toggleFavorite(a.user_id)}
                      className={favoriteIds.has(a.user_id) ? "text-maroon" : "text-ink-soft"}
                      title="Save to favorites"
                    >
                      {favoriteIds.has(a.user_id) ? "♥" : "♡"}
                    </button>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 text-sm">
                <span className="text-gold">★</span>
                <span className="font-semibold">{a.rating_avg || "New"}</span>
                {a.rating_count > 0 && <span className="text-ink-soft">({a.rating_count})</span>}
                <span className="text-ink-soft mx-1">·</span>
                <span className="text-ink-soft">{a.distance_km} km</span>
                <span className="text-ink-soft mx-1">·</span>
                <span className="text-maroon-soft">~{a.eta_minutes} min</span>
              </div>
              {a.bio && <p className="text-sm text-ink-soft line-clamp-2">{a.bio}</p>}
              {a.portfolio_urls && (
                <div className="flex gap-1.5 mt-1">
                  {a.portfolio_urls
                    .split(",")
                    .filter(Boolean)
                    .slice(0, 4)
                    .map((url, i, arr) => (
                      <button
                        key={url}
                        type="button"
                        onClick={() => setLightbox({ images: arr, index: i })}
                        className="w-11 h-11 rounded-lg overflow-hidden border border-line flex-none"
                      >
                        <img src={url} alt="" className="w-full h-full object-cover" />
                      </button>
                    ))}
                </div>
              )}
              {user?.role === "consumer" ? (
                <Link href={`/booking/${a.user_id}`} className="btn-primary text-center mt-1 text-sm">
                  Book This Artist
                </Link>
              ) : (
                <Link href="/login" className="btn-secondary text-center mt-1 text-sm">
                  Log in to book
                </Link>
              )}
            </div>
          </div>
        ))}
        {coords && !loading && artists.length === 0 && !error && (
          <p className="text-sm text-ink-soft">No approved artists within {SEARCH_RADIUS_KM} km yet.</p>
        )}
      </div>

      <Lightbox
        images={lightbox?.images ?? null}
        index={lightbox?.index ?? 0}
        onClose={() => setLightbox(null)}
        onIndexChange={(i) => setLightbox((prev) => ({ ...prev, index: i }))}
      />
    </div>
  );
}
