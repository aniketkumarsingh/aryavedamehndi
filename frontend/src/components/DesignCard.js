import Link from "next/link";
import { categoryLabel, coverageLabel, formatDuration, formatPriceRange, styleLabel } from "@/lib/designs";

/** Catalog design tile - photo, name, category, price range, duration.
 * `imageUrl` overrides the catalog photo (an artist profile shows the
 * artist's own photo of the design instead). */
export default function DesignCard({ design, imageUrl, href, footer }) {
  const src = imageUrl || design.image_url;
  const body = (
    <>
      <div className="aspect-square bg-ivory border-b border-line flex items-center justify-center overflow-hidden relative">
        {!imageUrl && design.image_kind === "illustration" && (
          <span className="absolute top-2 left-2 chip bg-ivory-raised/90 text-[10px] font-semibold" title="AI illustration - not a photo of a real mehndi">
            Illustration
          </span>
        )}
        {!imageUrl && (design.image_count > 1 || design.spin_frame_count >= 8) && (
          <span className="absolute top-2 right-2 flex gap-1">
            {design.spin_frame_count >= 8 && <span className="chip bg-ivory-raised/90 text-[10px]">360°</span>}
            {design.image_count > 1 && (
              <span className="chip bg-ivory-raised/90 text-[10px]" title={`${design.image_count} photos`}>
                📷 {design.image_count}
              </span>
            )}
          </span>
        )}
        {src ? (
          <img src={src} alt={design.name} className="w-full h-full object-cover" loading="lazy" />
        ) : (
          <img src="/patterns/mandala.svg" alt="" aria-hidden="true" className="w-1/2 opacity-30" />
        )}
      </div>
      <div className="p-3 flex flex-col gap-1">
        <span className="chip self-start text-[11px]">{categoryLabel(design.category)}</span>
        <h3 className="font-semibold leading-snug">{design.name}</h3>
        {(design.style || design.coverage) && (
          <p className="text-xs text-ink-soft">{[design.style && styleLabel(design.style), design.coverage && coverageLabel(design.coverage)].filter(Boolean).join(" · ")}</p>
        )}
        <p className="text-sm font-semibold text-maroon-soft">{formatPriceRange(design.price_min, design.price_max)}</p>
        <p className="text-xs text-ink-soft">~{formatDuration(design.duration_minutes)}</p>
        {footer}
      </div>
    </>
  );

  return href ? (
    <Link href={href} className="card overflow-hidden flex flex-col hover:ring-2 hover:ring-gold transition-shadow">
      {body}
    </Link>
  ) : (
    <div className="card overflow-hidden flex flex-col">{body}</div>
  );
}
