import { useEffect, useRef, useState } from "react";
import DesignViewer from "@/components/DesignViewer";
import PhotoCredit from "@/components/PhotoCredit";
import SpinViewer from "@/components/SpinViewer";
import { swipeDirection, tiltFromPointer } from "@/lib/viewer";

const KIND_LABEL = { detail: "Close-up", angle: "Angle", illustration: "Illustration", ai_photo: "Realistic AI preview", photo: "Photo" };

/** The design page's photo gallery: the main photo plus every extra view
 * (angles, close-ups, the illustrated version), with thumbnails, swipe, a
 * gentle hover tilt, a "Zoom view" button opening the full-screen viewer
 * (full-resolution zoom), and a "360 view" when turntable frames exist. */
export default function DesignGallery({ design }) {
  const views = [
    ...(design.image_url
      ? [
          design.image_kind === "illustration"
            ? { url: design.image_url, hdUrl: design.image_hd_url, label: "Illustration", kind: "illustration", credit: design.image_credit }
            : { url: design.image_url, hdUrl: design.image_hd_url, label: "Main photo", kind: "photo", credit: design.image_credit },
        ]
      : []),
    ...(design.images || []).map((i) => ({ url: i.url, hdUrl: i.hd_url, label: i.label || KIND_LABEL[i.kind], kind: i.kind, credit: i.credit })),
  ];
  const spinFrames = (design.spin_frames || []).map((f) => ({ url: f.url, hdUrl: f.hd_url }));
  const [spinOpen, setSpinOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [viewerIndex, setViewerIndex] = useState(null);
  const [tilt, setTilt] = useState({ rx: 0, ry: 0 });
  const stageRef = useRef(null);
  const swipe = useRef(null);
  const justSwiped = useRef(false);
  const thumbsRef = useRef(null);

  useEffect(() => setIndex(0), [design.id]);

  // Keep the active thumbnail visible in the strip.
  useEffect(() => {
    thumbsRef.current?.children[index]?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [index]);

  if (views.length === 0) {
    return (
      <div className="card overflow-hidden aspect-square bg-ivory flex items-center justify-center">
        <img src="/patterns/mandala.svg" alt="" aria-hidden="true" className="w-1/2 opacity-30" />
      </div>
    );
  }

  const current = views[Math.min(index, views.length - 1)];
  const step = (d) => setIndex((i) => (i + d + views.length) % views.length);

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={stageRef}
        className="card overflow-hidden aspect-square bg-ivory relative group touch-pan-y"
        style={{ perspective: "1000px" }}
        onPointerMove={(e) => {
          if (e.pointerType !== "mouse" || !stageRef.current) return;
          const t = tiltFromPointer(e.clientX, e.clientY, stageRef.current.getBoundingClientRect(), 6);
          setTilt(t);
        }}
        onPointerLeave={() => setTilt({ rx: 0, ry: 0 })}
        onPointerDown={(e) => (swipe.current = { x: e.clientX, y: e.clientY })}
        onPointerUp={(e) => {
          if (!swipe.current) return;
          const dir = swipeDirection(e.clientX - swipe.current.x, e.clientY - swipe.current.y);
          swipe.current = null;
          if (dir) {
            justSwiped.current = true; // the click that follows shouldn't open the viewer
            step(dir);
          }
        }}
      >
        <button
          type="button"
          className="absolute inset-0 w-full h-full cursor-zoom-in"
          onClick={() => {
            if (justSwiped.current) {
              justSwiped.current = false;
              return;
            }
            setViewerIndex(index);
          }}
          aria-label={`Open ${current.label} in zoom view`}
        >
          <img
            src={current.url}
            alt={`${design.name} - ${current.label}`}
            className="w-full h-full object-cover motion-safe:transition-transform motion-safe:duration-150"
            style={{ transform: `rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg) scale(${tilt.rx || tilt.ry ? 1.04 : 1})` }}
          />
        </button>
        <span className="absolute top-3 left-3 chip bg-ivory-raised/90 text-[11px] pointer-events-none">{current.label}</span>
        <div className="absolute bottom-3 right-3 flex gap-2">
          {spinFrames.length >= 8 && (
            <button type="button" onClick={() => setSpinOpen(true)} className="btn-primary text-xs px-3 py-1.5 shadow-lg">
              ⟳ 360° view
            </button>
          )}
          <button type="button" onClick={() => setViewerIndex(index)} className="btn-primary text-xs px-3 py-1.5 shadow-lg">
            🔍 Zoom view
          </button>
        </div>
        {views.length > 1 && (
          <>
            <span className="absolute bottom-3 left-3 chip bg-ivory-raised/90 text-[11px] pointer-events-none">
              {index + 1} / {views.length}
            </span>
            <button
              type="button"
              onClick={() => step(-1)}
              className="absolute left-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-ivory-raised/90 text-maroon text-xl shadow sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100 transition-opacity"
              aria-label="Previous photo"
            >
              ‹
            </button>
            <button
              type="button"
              onClick={() => step(1)}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-ivory-raised/90 text-maroon text-xl shadow sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100 transition-opacity"
              aria-label="Next photo"
            >
              ›
            </button>
          </>
        )}
      </div>

      <PhotoCredit credit={current.credit} illustration={current.kind === "illustration"} aiPhoto={current.kind === "ai_photo"} />

      {views.length > 1 && (
        <div ref={thumbsRef} className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Design photos">
          {views.map((v, i) => (
            <button
              key={v.url}
              type="button"
              role="tab"
              aria-selected={i === index}
              onClick={() => setIndex(i)}
              className={`flex-none w-20 rounded-lg overflow-hidden border-2 text-left ${i === index ? "border-maroon" : "border-line hover:border-gold"}`}
              title={v.label}
            >
              <img src={v.url} alt="" className="w-full aspect-square object-cover" loading="lazy" />
              <span className="block text-[10px] leading-tight px-1 py-0.5 truncate">{v.label}</span>
            </button>
          ))}
        </div>
      )}

      <DesignViewer views={views} index={viewerIndex} onIndexChange={setViewerIndex} onClose={() => setViewerIndex(null)} title={design.name} />
      <SpinViewer frames={spinFrames} open={spinOpen} onClose={() => setSpinOpen(false)} title={design.name} />
    </div>
  );
}
