"""Measurements and quality issues. All metrics are taken at a fixed analysis
size so numbers are comparable between photos of different resolutions."""
from __future__ import annotations

import math

import cv2
import numpy as np

ANALYSIS_SIDE = 1024
SEVERITY_PENALTY = {"error": 25, "warn": 10, "info": 2}


def resize_long(arr: np.ndarray, side: int = ANALYSIS_SIDE) -> np.ndarray:
    h, w = arr.shape[:2]
    scale = side / max(h, w)
    if abs(scale - 1) < 1e-3:
        return arr
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(arr, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=interp)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.ascontiguousarray(rgb, dtype=np.float32), cv2.COLOR_RGB2Lab)


def from_lab(lab: np.ndarray) -> np.ndarray:
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0.0, 1.0)


def _subject_select(mask: np.ndarray) -> np.ndarray:
    sel = mask > 0.5
    return sel if sel.sum() >= 0.002 * sel.size else np.ones_like(sel)


def subject_stats(lab: np.ndarray, mask: np.ndarray) -> dict:
    """Colour statistics of the subject. The 'anchor' is the brighter 40% of
    subject pixels (skin, paper, fabric) so that dense dark detail - henna,
    print, shadows - doesn't drag exposure and white balance around."""
    sel = _subject_select(mask)
    L = lab[..., 0][sel]
    cut = np.percentile(L, 60)
    anchor = sel & (lab[..., 0] >= cut)
    a, b = lab[..., 1][anchor], lab[..., 2][anchor]
    return {
        "L": float(np.median(lab[..., 0][anchor])),
        "L_median": float(np.median(L)),
        "L_std": float(L.std()),
        "a": float(a.mean()),
        "b": float(b.mean()),
        "chroma": float(np.sqrt(a**2 + b**2).mean()),
    }


def _noise_sigma(gray: np.ndarray) -> float:
    """Immerkaer's fast noise estimate (0-255 scale)."""
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    conv = cv2.filter2D(gray, -1, kernel)
    return float(math.sqrt(math.pi / 2) * np.abs(conv[1:-1, 1:-1]).sum() / (6 * (w - 2) * (h - 2)))


def _colorfulness(rgb255: np.ndarray, sel: np.ndarray) -> float:
    if sel.sum() < 50:
        return 0.0
    r, g, b = (rgb255[..., i][sel] for i in range(3))
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(math.hypot(rg.std(), yb.std()) + 0.3 * math.hypot(rg.mean(), yb.mean()))


def measure(rgb: np.ndarray, mask: np.ndarray, source_size: tuple[int, int] | None = None) -> dict:
    """rgb: float HxWx3 [0,1]; mask: float HxW [0,1] (same size)."""
    h, w = rgb.shape[:2]
    small = resize_long(rgb.astype(np.float32, copy=False))
    m = cv2.resize(mask.astype(np.float32), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_LINEAR)
    lab = to_lab(small)
    sel = _subject_select(m)
    bg = ~(m > 0.5)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY) * 255.0
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    edges = cv2.Canny(gray.astype(np.uint8), 60, 150) > 0

    hard = m > 0.5
    fill = float(hard.mean())
    if hard.any():
        ys, xs = np.nonzero(hard)
        sh, sw = hard.shape
        bbox = [float(xs.min() / sw), float(ys.min() / sh), float((xs.max() + 1) / sw), float((ys.max() + 1) / sh)]
        tol = 0.01
        touches = [side for side, hit in (("left", bbox[0] <= tol), ("top", bbox[1] <= tol), ("right", bbox[2] >= 1 - tol), ("bottom", bbox[3] >= 1 - tol)) if hit]
    else:
        bbox, touches = None, []

    # Sharpness is judged only where there are edges (the design's lines),
    # so a crisp but minimal design on lots of bare skin isn't called blurry.
    edge_zone = cv2.dilate(cv2.Canny(gray.astype(np.uint8), 20, 60), np.ones((5, 5), np.uint8)) > 0
    sharp_sel = sel & edge_zone
    if sharp_sel.sum() < 0.005 * sel.sum():
        sharp_sel = sel

    L = lab[..., 0][sel]
    stats = subject_stats(lab, m)
    sw_, sh_ = source_size or (w, h)
    return {
        "size": [int(sw_), int(sh_)],
        "aspect": round(sw_ / sh_, 3),
        "subject": {"fill": round(fill, 4), "bbox": [round(v, 4) for v in bbox] if bbox else None, "touches": touches},
        "sharpness": round(float(lap[sharp_sel].var()), 1),
        "noise": round(_noise_sigma(gray), 2),
        "exposure": {
            "L": round(stats["L"], 2),
            "L_median": round(stats["L_median"], 2),
            "L_std": round(stats["L_std"], 2),
            "clip_high": round(float((L > 98).mean()), 4),
            "clip_low": round(float((L < 3).mean()), 4),
        },
        "color": {"a": round(stats["a"], 2), "b": round(stats["b"], 2), "chroma": round(stats["chroma"], 2)},
        "background": {
            "share": round(float(bg.mean()), 4),
            "busy": round(float(edges[bg].mean()) if bg.any() else 0.0, 4),
            "colorfulness": round(_colorfulness(small * 255.0, bg), 1),
        },
    }


def issues(metrics: dict, cfg: dict) -> list[dict]:
    q, ref = cfg["quality"], cfg["color"]["reference"]
    out: list[dict] = []

    def add(code, severity, message):
        out.append({"code": code, "severity": severity, "message": message})

    long_side = max(metrics["size"])
    if long_side < q["min_long_side"]:
        sev = "error" if long_side < q["min_long_side"] / 2 else "warn"
        add("low_resolution", sev, f"{long_side}px on the long side; {q['min_long_side']}px or more recommended")
    if metrics["sharpness"] < q["min_sharpness"]:
        sev = "error" if metrics["sharpness"] < q["min_sharpness"] / 3 else "warn"
        add("blurry", sev, f"possibly out of focus (edge sharpness {metrics['sharpness']}, min {q['min_sharpness']}) - check by eye")
    exp = metrics["exposure"]
    if exp["L"] < 50:
        add("underexposed", "warn", f"subject is dark (L {exp['L']})")
    elif exp["L"] > 92 or exp["clip_high"] > 0.05:
        add("overexposed", "warn", f"subject highlights are blown ({exp['clip_high']:.0%} clipped)")
    if ref:
        da, db = metrics["color"]["a"] - ref["a"], metrics["color"]["b"] - ref["b"]
        if math.hypot(da, db) > 8:
            add("color_cast", "warn", f"colour is off the reference look (a {da:+.1f}, b {db:+.1f})")
    bg = metrics["background"]
    if bg["share"] > 0.05 and (bg["busy"] > q["max_background_busy"] or bg["colorfulness"] > q["max_background_colorfulness"]):
        add("busy_background", "warn", f"background is busy or colourful (edges {bg['busy']:.2f}, colour {bg['colorfulness']})")
    subj = metrics["subject"]
    if subj["bbox"] is None:
        add("no_subject", "error", "no clear subject found")
    elif subj["fill"] < q["min_fill"]:
        add("small_subject", "warn", f"subject fills only {subj['fill']:.0%} of the frame")
    if metrics["noise"] > 6:
        add("noisy", "info", f"visible noise (sigma {metrics['noise']})")
    return out


def score(found: list[dict]) -> int:
    return max(0, 100 - sum(SEVERITY_PENALTY[i["severity"]] for i in found))


def analyze_image(rgb: np.ndarray, mask: np.ndarray, cfg: dict, source_size=None) -> dict:
    metrics = measure(rgb, mask, source_size)
    found = issues(metrics, cfg)
    return {**metrics, "issues": found, "score": score(found)}


def consistency(reports: list[dict]) -> dict:
    """Spread (standard deviation) of the look across a set - lower is more uniform."""
    if not reports:
        return {}
    cols = {
        "subject_L": [r["exposure"]["L"] for r in reports],
        "subject_a": [r["color"]["a"] for r in reports],
        "subject_b": [r["color"]["b"] for r in reports],
        "background_colorfulness": [r["background"]["colorfulness"] for r in reports],
        "background_busy": [r["background"]["busy"] for r in reports],
        "aspect": [r["aspect"] for r in reports],
    }
    return {k: round(float(np.std(v)), 3) for k, v in cols.items()}
