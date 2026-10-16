import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState([]);
  const [error, setError] = useState("");

  function load() {
    api.get("/favorites").then(setFavorites).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function remove(artistId) {
    try {
      await api.del(`/favorites/${artistId}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl">My Favorite Artists</h1>
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="grid sm:grid-cols-2 gap-4">
        {favorites.map((f) => (
          <div key={f.artist_id} className="card overflow-hidden flex gap-4 p-4">
            <img
              src={f.profile_photo_url || "/avatars/preset-1.svg"}
              alt=""
              className="h-20 w-20 rounded-2xl object-cover border border-line flex-none"
            />
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <div className="flex justify-between items-start gap-2">
                <h3 className="font-semibold truncate">{f.name || "Mehndi Artist"}</h3>
                <button type="button" onClick={() => remove(f.artist_id)} className="text-maroon" title="Remove from favorites">
                  ♥
                </button>
              </div>
              <div className="flex items-center gap-1 text-sm">
                <span className="text-gold">★</span>
                <span className="font-semibold">{f.rating_avg || "New"}</span>
                {f.rating_count > 0 && <span className="text-ink-soft">({f.rating_count})</span>}
              </div>
              {f.bio && <p className="text-sm text-ink-soft line-clamp-2">{f.bio}</p>}
              <Link href={`/booking/${f.artist_id}`} className="btn-primary text-center mt-1 text-sm">
                Book This Artist
              </Link>
            </div>
          </div>
        ))}
        {favorites.length === 0 && (
          <p className="text-sm text-ink-soft">
            No favorites yet —{" "}
            <Link href="/discover" className="underline text-maroon-soft">
              find an artist
            </Link>{" "}
            and tap the heart to save them here.
          </p>
        )}
      </div>
    </div>
  );
}
