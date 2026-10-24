import { useEffect, useRef, useState } from "react";
import { clampPan, maxZoomFor, pinchZoom, spinFrameFromDrag, zoomAt } from "@/lib/viewer";

const UNZOOMED = { zoom: 1, pan: { x: 0, y: 0 } };
const AUTO_SPIN_MS = 110; // per frame - about 4 s per turn with 36 frames

/** Full-screen 360-degree view from turntable photos: drag sideways to
 * turn the design all the way round, or let it auto-rotate. Any frame can
 * be zoomed (loading that frame's full-resolution copy) - drag then pans
 * instead of spinning, until zoomed back out.
 *
 * frames: [{ url, hdUrl? }] in rotation order. */
export default function SpinViewer({ frames, open, onClose, title }) {
  const frameRef = useRef(null);
  const closeRef = useRef(null);
  const pointers = useRef(new Map());
  const gesture = useRef(null);
  const [index, setIndex] = useState(0);
  const [loaded, setLoaded] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [view, setView] = useState(UNZOOMED);
  const [hd, setHd] = useState({ url: null, natural: 0 });
  const [frameWidth, setFrameWidth] = useState(0);
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const ready = loaded >= frames.length;
  const current = frames[index];
  const zoomed = view.zoom > 1;
  const maxZoom = maxZoomFor(hd.url === current?.hdUrl ? hd.natural : 0, frameWidth, dpr);

  // Preload every frame so spinning never flickers.
  useEffect(() => {
    if (!open) return;
    setIndex(0);
    setLoaded(0);
    setView(UNZOOMED);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let count = 0;
    const imgs = frames.map((f) => {
      const img = new Image();
      img.onload = img.onerror = () => setLoaded(++count);
      img.src = f.url;
      return img;
    });
    setPlaying(!reduce);
    return () => imgs.forEach((img) => (img.onload = img.onerror = null));
  }, [open, frames]);

  useEffect(() => {
    if (!open || !playing || !ready || zoomed) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % frames.length), AUTO_SPIN_MS);
    return () => clearInterval(t);
  }, [open, playing, ready, zoomed, frames.length]);

  // Zooming in loads the current frame's full-resolution copy.
  useEffect(() => {
    if (!zoomed || !current?.hdUrl || hd.url === current.hdUrl) return;
    const img = new Image();
    img.onload = () => setHd({ url: current.hdUrl, natural: img.naturalWidth });
    img.src = current.hdUrl;
  }, [zoomed, current?.hdUrl, hd.url]);

  useEffect(() => {
    const el = frameRef.current;
    if (!el || !open) return;
    const ro = new ResizeObserver(([entry]) => setFrameWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement;
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e) {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function step(d) {
    setPlaying(false);
    setView(UNZOOMED);
    setIndex((i) => (i + d + frames.length) % frames.length);
  }

  function zoomTo(nextZoom, clientX, clientY) {
    const r = frameRef.current?.getBoundingClientRect();
    if (!r) return;
    // Until the full-res copy is in, allow a first 2x step so it starts loading.
    const limit = current?.hdUrl && hd.url !== current.hdUrl ? 2 : maxZoom;
    const point = clientX != null ? { x: clientX - r.left - r.width / 2, y: clientY - r.top - r.height / 2 } : { x: 0, y: 0 };
    setPlaying(false);
    setView((v) => zoomAt(v, Math.min(nextZoom, limit), point, r.width, r.height));
  }

  function onPointerDown(e) {
    frameRef.current?.setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    setPlaying(false);
    gesture.current =
      pts.length === 2
        ? { type: "pinch", startZoom: view.zoom, startDist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) }
        : { type: "drag", startX: e.clientX, startY: e.clientY, startIndex: index, startPan: view.pan };
  }

  function onPointerMove(e) {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    const r = frameRef.current?.getBoundingClientRect();
    if (!g || !r) return;
    if (g.type === "pinch") {
      const pts = [...pointers.current.values()];
      if (pts.length < 2) return;
      const z = Math.min(pinchZoom(g.startZoom, g.startDist, Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)), Math.max(maxZoom, 2));
      setView((v) => (z <= 1 ? UNZOOMED : { zoom: z, pan: clampPan(v.pan, z, r.width, r.height) }));
      return;
    }
    const dx = e.clientX - g.startX;
    if (zoomed) {
      setView((v) => ({ ...v, pan: clampPan({ x: g.startPan.x + dx, y: g.startPan.y + (e.clientY - g.startY) }, v.zoom, r.width, r.height) }));
    } else {
      setIndex(spinFrameFromDrag(g.startIndex, dx, r.width, frames.length));
    }
  }

  function onPointerUp(e) {
    pointers.current.delete(e.pointerId);
    if (!pointers.current.size) gesture.current = null;
  }

  useEffect(() => {
    const el = frameRef.current;
    if (!el || !open) return;
    function onWheel(e) {
      e.preventDefault();
      zoomTo(view.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  if (!open || frames.length === 0) return null;

  const src = zoomed && hd.url === current.hdUrl ? hd.url : current.url;

  return (
    <div className="fixed inset-0 z-50 bg-[#1b0f0c] flex flex-col text-white select-none" role="dialog" aria-modal="true" aria-label={`${title} - 360 view`}>
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{title}</p>
          <p className="text-xs text-white/70">
            360° view · {Math.round((index / frames.length) * 360)}°
          </p>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} className="w-10 h-10 rounded-full hover:bg-white/10 text-2xl leading-none flex-none" aria-label="Close 360 view">
          ×
        </button>
      </div>

      <div className="flex-1 flex items-center justify-center px-2 min-h-0">
        <div
          ref={frameRef}
          className="relative aspect-square h-full max-h-[min(78vh,92vw)] max-w-full overflow-hidden rounded-2xl touch-none bg-black/20"
          style={{ cursor: zoomed ? "grab" : "ew-resize" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={(e) => zoomTo(zoomed ? 1 : 2, e.clientX, e.clientY)}
        >
          <img
            src={src}
            alt={`${title} - ${Math.round((index / frames.length) * 360)} degrees`}
            draggable={false}
            className="absolute inset-0 w-full h-full object-cover"
            style={{ transform: `translate3d(${view.pan.x}px, ${view.pan.y}px, 0) scale(${view.zoom})` }}
          />
          {!ready && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/50 text-sm">
              <span>Loading 360° view…</span>
              <span className="text-xs text-white/70">
                {loaded} / {frames.length}
              </span>
            </div>
          )}
          {ready && !zoomed && (
            <span className="absolute bottom-3 left-1/2 -translate-x-1/2 text-[11px] bg-black/40 rounded-full px-3 py-1 pointer-events-none">
              ⟷ Drag to turn
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col items-center gap-2 px-4 py-3">
        <input
          type="range"
          min={0}
          max={frames.length - 1}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            setView(UNZOOMED);
            setIndex(Number(e.target.value));
          }}
          className="w-full max-w-md accent-[#D9A34E]"
          aria-label="Rotation"
        />
        <div className="flex items-center gap-2 text-sm flex-wrap justify-center">
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={() => step(-1)} aria-label="Turn left">
            ‹
          </button>
          <button type="button" className="px-4 py-1.5 rounded-full bg-[#A9761E] hover:bg-[#c08a2a]" onClick={() => setPlaying((p) => !p)} disabled={!ready || zoomed}>
            {playing ? "❚❚ Pause" : "▶ Rotate"}
          </button>
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={() => step(1)} aria-label="Turn right">
            ›
          </button>
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={() => zoomTo(zoomed ? 1 : 2)}>
            {zoomed ? "Zoom out" : "Zoom in"}
          </button>
        </div>
        <p className="text-[11px] text-white/60 text-center">Drag sideways to turn · scroll, pinch or double-click to zoom · space to play/pause</p>
      </div>
    </div>
  );
}
