import { useEffect } from "react";

/** Full-screen image viewer with prev/next navigation. Pass `images`
 * (array of URLs) and `index` (currently shown), plus `onClose` and
 * `onIndexChange`. Renders nothing when `images` is empty/null. */
export default function Lightbox({ images, index, onClose, onIndexChange }) {
  useEffect(() => {
    if (images == null) return;
    function onKey(e) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onIndexChange((index + 1) % images.length);
      if (e.key === "ArrowLeft") onIndexChange((index - 1 + images.length) % images.length);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images, index, onClose, onIndexChange]);

  if (images == null || images.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 text-white text-2xl leading-none w-10 h-10 flex items-center justify-center rounded-full hover:bg-white/10"
        aria-label="Close"
      >
        ×
      </button>

      {images.length > 1 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index - 1 + images.length) % images.length);
          }}
          className="absolute left-2 sm:left-6 text-white text-3xl w-12 h-12 flex items-center justify-center rounded-full hover:bg-white/10"
          aria-label="Previous"
        >
          ‹
        </button>
      )}

      <img
        src={images[index]}
        alt=""
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] max-w-[90vw] object-contain rounded-lg"
      />

      {images.length > 1 && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onIndexChange((index + 1) % images.length);
          }}
          className="absolute right-2 sm:right-6 text-white text-3xl w-12 h-12 flex items-center justify-center rounded-full hover:bg-white/10"
          aria-label="Next"
        >
          ›
        </button>
      )}

      {images.length > 1 && (
        <div className="absolute bottom-4 text-white text-xs bg-black/40 rounded-full px-3 py-1">
          {index + 1} / {images.length}
        </div>
      )}
    </div>
  );
}
