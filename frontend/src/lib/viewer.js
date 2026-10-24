// Pure math for the design viewer (components/DesignViewer.js) - kept
// separate so it's unit-testable without a browser.

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 5;
export const MAX_TILT_DEG = 16;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Tilt (degrees) so the image leans toward the pointer: pointer on the
 * right edge -> rotateY +max, top edge -> rotateX +max. */
export function tiltFromPointer(clientX, clientY, rect, max = MAX_TILT_DEG) {
  const nx = clamp((clientX - rect.left) / rect.width, 0, 1) * 2 - 1;
  const ny = clamp((clientY - rect.top) / rect.height, 0, 1) * 2 - 1;
  return { rx: round(-ny * max), ry: round(nx * max) };
}

/** Tilt from phone motion. beta/gamma are the deviceorientation angles;
 * `base` is the reading when tilt was switched on, so the phone's resting
 * angle counts as "flat". */
export function tiltFromOrientation(beta, gamma, base, max = MAX_TILT_DEG) {
  const scale = max / 25; // 25 degrees of phone tilt = full image tilt
  return {
    rx: round(clamp(-(beta - base.beta) * scale, -max, max)),
    ry: round(clamp((gamma - base.gamma) * scale, -max, max)),
  };
}

export function clampZoom(zoom) {
  return clamp(zoom, MIN_ZOOM, MAX_ZOOM);
}

/** Pan is limited so the zoomed image always covers the frame. */
export function clampPan(pan, zoom, width, height) {
  const maxX = ((zoom - 1) * width) / 2;
  const maxY = ((zoom - 1) * height) / 2;
  return { x: round(clamp(pan.x, -maxX, maxX)), y: round(clamp(pan.y, -maxY, maxY)) };
}

/** Zoom while keeping the point under the cursor fixed. `point` is
 * relative to the frame centre. */
export function zoomAt(state, nextZoom, point, width, height) {
  const zoom = clampZoom(nextZoom);
  if (zoom === MIN_ZOOM) return { zoom, pan: { x: 0, y: 0 } };
  const ratio = zoom / state.zoom;
  const pan = {
    x: point.x - (point.x - state.pan.x) * ratio,
    y: point.y - (point.y - state.pan.y) * ratio,
  };
  return { zoom, pan: clampPan(pan, zoom, width, height) };
}

/** Pinch zoom factor from the start and current distance between two touches. */
export function pinchZoom(startZoom, startDistance, distance) {
  if (!startDistance) return startZoom;
  return clampZoom(startZoom * (distance / startDistance));
}

/** Highest zoom that still shows real detail: the image's own pixels
 * spread over the frame's device pixels, plus a little headroom (beyond
 * that a photo only gets blurrier, so zoom stops there). */
export function maxZoomFor(naturalWidth, frameWidth, devicePixelRatio = 1, headroom = 1.25) {
  if (!naturalWidth || !frameWidth) return MIN_ZOOM;
  const native = naturalWidth / (frameWidth * devicePixelRatio);
  return Math.round(clamp(native * headroom, MIN_ZOOM, MAX_ZOOM) * 100) / 100;
}

/** 360 view: which frame to show after dragging `dx` pixels from
 * `startIndex`. Dragging the full frame width turns the design once all
 * the way round; dragging right turns it the same way as the frames run. */
export function spinFrameFromDrag(startIndex, dx, frameWidth, count) {
  if (!count || !frameWidth) return startIndex;
  const step = Math.round((dx / frameWidth) * count);
  return (((startIndex - step) % count) + count) % count;
}

/** -1 / +1 when a horizontal drag is long enough to count as a swipe. */
export function swipeDirection(dx, dy, threshold = 50) {
  if (Math.abs(dx) < threshold || Math.abs(dx) < Math.abs(dy) * 1.5) return 0;
  return dx < 0 ? 1 : -1;
}

function round(v) {
  return Math.round(v * 100) / 100 || 0;
}
