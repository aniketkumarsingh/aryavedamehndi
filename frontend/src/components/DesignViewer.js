import { useCallback, useEffect, useRef, useState } from "react";
import {
  clampPan,
  maxZoomFor,
  pinchZoom,
  swipeDirection,
  tiltFromOrientation,
  tiltFromPointer,
  zoomAt,
} from "@/lib/viewer";

const FLAT = { rx: 0, ry: 0 };
const UNZOOMED = { zoom: 1, pan: { x: 0, y: 0 } };

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Full-screen zoom view of a design: the photo tilts toward the pointer
 * (or with the phone's motion) with a moving light sheen, and zooms -
 * wheel, pinch, double-tap or buttons - with drag to pan. Zoom loads the
 * full-resolution copy and stops where the photo runs out of real detail,
 * so it never shows broken pixels. Swipe / arrow keys move between views.
 *
 * views: [{ url, hdUrl?, label }]; open when `index` is a number. */
export default function DesignViewer({ views, index, onIndexChange, onClose, title }) {
  const frameRef = useRef(null);
  const closeRef = useRef(null);
  const pointers = useRef(new Map());
  const gesture = useRef(null);
  const [tilt, setTilt] = useState(FLAT);
  const [sheen, setSheen] = useState({ x: 50, y: 30 });
  const [view, setView] = useState(UNZOOMED);
  const [motion, setMotion] = useState("off"); // "off" | "on" | "denied"
  const [reduced, setReduced] = useState(false);
  const open = typeof index === "number" && views.length > 0;
  const current = open ? views[index] : null;
  // Read by the deviceorientation listener without re-subscribing.
  const zoomRef = useRef(1);
  zoomRef.current = view.zoom;
  // Full-resolution copy: preloaded on open, swapped in once it's ready.
  const [hdReady, setHdReady] = useState(false);
  const [natural, setNatural] = useState(0);
  const [frameWidth, setFrameWidth] = useState(0);
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const maxZoom = maxZoomFor(natural, frameWidth, dpr);
  const maxZoomRef = useRef(1);
  maxZoomRef.current = maxZoom;
  const cap = (z) => Math.min(z, maxZoomRef.current);

  useEffect(() => {
    setHdReady(false);
    setNatural(0);
    if (!current?.hdUrl) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      setNatural(img.naturalWidth);
      setHdReady(true);
    };
    img.src = current.hdUrl;
    return () => {
      cancelled = true;
    };
  }, [current?.hdUrl]);

  useEffect(() => {
    const el = frameRef.current;
    if (!el || !open) return;
    const ro = new ResizeObserver(([entry]) => setFrameWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  useEffect(() => setReduced(prefersReducedMotion()), []);

  const reset = useCallback(() => {
    setView(UNZOOMED);
    setTilt(FLAT);
  }, []);

  const go = useCallback(
    (step) => {
      reset();
      onIndexChange((index + step + views.length) % views.length);
    },
    [index, views.length, onIndexChange, reset]
  );

  function frameSize() {
    const r = frameRef.current?.getBoundingClientRect();
    return r ? { width: r.width, height: r.height, rect: r } : { width: 1, height: 1, rect: null };
  }

  function zoomTo(nextZoom, clientX, clientY) {
    const { width, height, rect } = frameSize();
    const point = rect && clientX != null ? { x: clientX - rect.left - width / 2, y: clientY - rect.top - height / 2 } : { x: 0, y: 0 };
    setView((v) => zoomAt(v, cap(nextZoom), point, width, height));
    setTilt(FLAT);
  }

  // Keyboard, scroll lock and focus while open.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement;
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e) {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "+" || e.key === "=") setView((v) => zoomAtCentre(v, v.zoom * 1.5));
      else if (e.key === "-") setView((v) => zoomAtCentre(v, v.zoom / 1.5));
      else if (e.key === "0") reset();
    }
    function zoomAtCentre(v, z) {
      const { width, height } = frameSize();
      return zoomAt(v, cap(z), { x: 0, y: 0 }, width, height);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
  }, [open, go, onClose, reset]);

  // Phone motion tilt (after the user switched it on).
  useEffect(() => {
    if (motion !== "on" || !open) return;
    let base = null;
    function onOrient(e) {
      if (e.beta == null || e.gamma == null) return;
      base = base || { beta: e.beta, gamma: e.gamma };
      if (zoomRef.current === 1) setTilt(tiltFromOrientation(e.beta, e.gamma, base));
    }
    window.addEventListener("deviceorientation", onOrient);
    return () => window.removeEventListener("deviceorientation", onOrient);
  }, [motion, open]);

  async function enableMotion() {
    try {
      // iOS needs an explicit permission prompt from a user gesture.
      if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
        const answer = await DeviceOrientationEvent.requestPermission();
        if (answer !== "granted") return setMotion("denied");
      }
      setMotion("on");
    } catch {
      setMotion("denied");
    }
  }

  // ---- pointer handling: tilt (mouse), pan (zoomed), swipe & pinch (touch)
  function onPointerDown(e) {
    frameRef.current?.setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    if (pts.length === 2) {
      gesture.current = { type: "pinch", startZoom: view.zoom, startDist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) };
    } else {
      gesture.current = { type: "drag", startX: e.clientX, startY: e.clientY, startPan: view.pan, moved: false };
    }
  }

  function onPointerMove(e) {
    const { width, height, rect } = frameSize();
    if (!pointers.current.has(e.pointerId)) {
      // Hovering mouse: tilt toward the pointer.
      if (e.pointerType === "mouse" && rect && view.zoom === 1 && !reduced) {
        setTilt(tiltFromPointer(e.clientX, e.clientY, rect));
        setSheen({ x: ((e.clientX - rect.left) / width) * 100, y: ((e.clientY - rect.top) / height) * 100 });
      }
      return;
    }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    if (!g) return;
    if (g.type === "pinch") {
      const pts = [...pointers.current.values()];
      if (pts.length < 2) return;
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const z = cap(pinchZoom(g.startZoom, g.startDist, dist));
      setView((v) => (z === 1 ? UNZOOMED : { zoom: z, pan: clampPan(v.pan, z, width, height) }));
      setTilt(FLAT);
      return;
    }
    const dx = e.clientX - g.startX;
    const dy = e.clientY - g.startY;
    if (Math.abs(dx) + Math.abs(dy) > 6) g.moved = true;
    if (view.zoom > 1) {
      setView((v) => ({ ...v, pan: clampPan({ x: g.startPan.x + dx, y: g.startPan.y + dy }, v.zoom, width, height) }));
    }
  }

  function onPointerUp(e) {
    const g = gesture.current;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size > 0) return;
    gesture.current = null;
    if (g?.type === "drag" && view.zoom === 1 && views.length > 1) {
      const dir = swipeDirection(e.clientX - g.startX, e.clientY - g.startY);
      if (dir) go(dir);
    }
  }

  function onPointerLeave(e) {
    if (e.pointerType === "mouse" && !pointers.current.size) setTilt(FLAT);
  }

  function onWheel(e) {
    e.preventDefault();
    zoomTo(view.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
  }

  // React's onWheel is passive, so preventDefault needs a native listener.
  useEffect(() => {
    const el = frameRef.current;
    if (!el || !open) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  if (!open) return null;

  const zoomed = view.zoom > 1;
  const transform = `perspective(1100px) rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg) translate3d(${view.pan.x}px, ${view.pan.y}px, 0) scale(${view.zoom})`;
  const isTouch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

  return (
    <div className="fixed inset-0 z-50 bg-[#1b0f0c] flex flex-col text-white select-none" role="dialog" aria-modal="true" aria-label={`${title} - zoom view`}>
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{title}</p>
          <p className="text-xs text-white/70">
            {current.label || "Main photo"} · {index + 1} / {views.length}
          </p>
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          className="w-10 h-10 rounded-full hover:bg-white/10 text-2xl leading-none flex-none"
          aria-label="Close zoom view"
        >
          ×
        </button>
      </div>

      <div className="flex-1 flex items-center justify-center px-2 sm:px-14 min-h-0 relative">
        {views.length > 1 && (
          <button type="button" onClick={() => go(-1)} className="absolute left-1 sm:left-3 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 text-2xl" aria-label="Previous view">
            ‹
          </button>
        )}

        <div
          ref={frameRef}
          className="relative aspect-square h-full max-h-[min(78vh,92vw)] max-w-full overflow-hidden rounded-2xl touch-none"
          style={{ cursor: zoomed ? "grab" : "zoom-in" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerLeave}
          onDoubleClick={(e) => zoomTo(zoomed ? 1 : 2.5, e.clientX, e.clientY)}
        >
          <div
            className="absolute inset-0 will-change-transform"
            style={{
              transform,
              transformStyle: "preserve-3d",
              transition: gesture.current ? "none" : "transform 120ms ease-out",
              boxShadow: `${-tilt.ry * 1.5}px ${tilt.rx * 1.5 + 18}px 40px rgba(0,0,0,0.45)`,
            }}
          >
            <img
              src={hdReady ? current.hdUrl : current.url}
              alt={current.label || title}
              draggable={false}
              className="w-full h-full object-cover rounded-2xl"
              onLoad={(e) => !current.hdUrl && setNatural(e.currentTarget.naturalWidth)}
            />
            {!zoomed && !reduced && (
              <div
                className="absolute inset-0 rounded-2xl pointer-events-none mix-blend-soft-light"
                style={{ background: `radial-gradient(circle at ${sheen.x}% ${sheen.y}%, rgba(255,255,255,0.55), transparent 55%)` }}
              />
            )}
          </div>
        </div>

        {views.length > 1 && (
          <button type="button" onClick={() => go(1)} className="absolute right-1 sm:right-3 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 text-2xl" aria-label="Next view">
            ›
          </button>
        )}
      </div>

      <div className="flex flex-col items-center gap-2 px-4 py-3">
        <div className="flex items-center gap-2 text-sm flex-wrap justify-center">
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={() => zoomTo(view.zoom / 1.5)} disabled={!zoomed} aria-label="Zoom out">
            −
          </button>
          <span className="w-12 text-center tabular-nums">{Math.round(view.zoom * 100)}%</span>
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={() => zoomTo(view.zoom * 1.5)} disabled={view.zoom >= maxZoom - 0.01} aria-label="Zoom in">
            +
          </button>
          <button type="button" className="px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20" onClick={reset}>
            Reset
          </button>
          {isTouch && !reduced && motion !== "on" && (
            <button type="button" className="px-3 py-1.5 rounded-full bg-[#A9761E] hover:bg-[#c08a2a]" onClick={enableMotion}>
              {motion === "denied" ? "Motion blocked" : "Tilt with phone"}
            </button>
          )}
        </div>
        {current.hdUrl && !hdReady && <p className="text-[11px] text-white/70">Loading full-resolution photo…</p>}
        {(hdReady || !current.hdUrl) && maxZoom <= 1.01 && (
          <p className="text-[11px] text-white/70">This photo is shown at its full detail - it can&apos;t be zoomed further.</p>
        )}
        {maxZoom > 1.01 && view.zoom >= maxZoom - 0.01 && <p className="text-[11px] text-[#D9A34E]">Full detail reached</p>}
        <p className="text-[11px] text-white/60 text-center">
          {isTouch ? "Pinch or double-tap to zoom · swipe for more views" : "Move the mouse to tilt · scroll or double-click to zoom · drag to pan"}
        </p>
        {views.length > 1 && (
          <div className="flex gap-2 overflow-x-auto max-w-full pb-1">
            {views.map((v, i) => (
              <button
                key={v.url}
                type="button"
                onClick={() => {
                  reset();
                  onIndexChange(i);
                }}
                className={`flex-none w-14 h-14 rounded-lg overflow-hidden border-2 ${i === index ? "border-[#D9A34E]" : "border-transparent opacity-70 hover:opacity-100"}`}
                aria-label={v.label || "Main photo"}
                aria-current={i === index}
              >
                <img src={v.url} alt="" className="w-full h-full object-cover" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
