"""Framing (where to crop) and backgrounds (keep, soften or replace)."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import hex_to_rgb

Region = tuple[float, float, float, float]  # x0, y0, x1, y1 in source pixels


def _grow(a: float, b: float, need: float, touch_a: bool, touch_b: bool):
    """Widen [a, b] by `need`, keeping a side flush if the subject leaves the frame there."""
    if touch_a and touch_b:
        return None
    if touch_a:
        return a, b + need
    if touch_b:
        return a - need, b
    return a - need / 2, b + need / 2


def _shrink(a: float, b: float, need: float, touch_a: bool, touch_b: bool):
    """Narrow [a, b] by `need`, cutting first where the subject already leaves the frame."""
    if touch_a and not touch_b:
        return a + need, b
    if touch_b and not touch_a:
        return a, b - need
    return a + need / 2, b - need / 2


def subject_region(mask: np.ndarray, img_w: int, img_h: int, aspect: float | None, margin: float, allow_pad: bool) -> Region | None:
    """Crop box around the subject. `mask` may be smaller than the image.

    Sides where the subject runs out of the photo (an arm leaving the frame)
    stay flush so the subject still runs off the edge; other sides get `margin`.
    With allow_pad the box may extend past the photo (filled with the new
    background); otherwise it is fitted inside the photo."""
    hard = mask > 0.5
    if hard.sum() < 0.002 * hard.size:
        return None
    mh, mw = hard.shape
    ys, xs = np.nonzero(hard)
    x0, x1 = np.percentile(xs, [0.2, 99.8])
    y0, y1 = np.percentile(ys, [0.2, 99.8])
    x1, y1 = x1 + 1, y1 + 1
    tol = 0.01
    touch = {"l": x0 <= tol * mw, "t": y0 <= tol * mh, "r": x1 >= (1 - tol) * mw, "b": y1 >= (1 - tol) * mh}
    sx, sy = img_w / mw, img_h / mh
    x0, x1, y0, y1 = x0 * sx, x1 * sx, y0 * sy, y1 * sy

    m = margin * max(x1 - x0, y1 - y0)
    x0 -= 0 if touch["l"] else m
    x1 += 0 if touch["r"] else m
    y0 -= 0 if touch["t"] else m
    y1 += 0 if touch["b"] else m

    if aspect:
        w, h = x1 - x0, y1 - y0
        if w / h < aspect:
            grown = _grow(x0, x1, h * aspect - w, touch["l"], touch["r"])
            if grown:
                x0, x1 = grown
            else:
                y0, y1 = _shrink(y0, y1, h - w / aspect, touch["t"], touch["b"])
        elif w / h > aspect:
            grown = _grow(y0, y1, w / aspect - h, touch["t"], touch["b"])
            if grown:
                y0, y1 = grown
            else:
                x0, x1 = _shrink(x0, x1, w - h * aspect, touch["l"], touch["r"])

    if not allow_pad:
        x0, y0, x1, y1 = fit_inside((x0, y0, x1, y1), img_w, img_h)
    return x0, y0, x1, y1


def fit_inside(region: Region, img_w: int, img_h: int) -> Region:
    x0, y0, x1, y1 = region
    w, h = x1 - x0, y1 - y0
    scale = min(1.0, img_w / w, img_h / h)
    if scale < 1.0:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = w * scale, h * scale
        x0, y0 = cx - w / 2, cy - h / 2
    x0 = min(max(x0, 0.0), img_w - w)
    y0 = min(max(y0, 0.0), img_h - h)
    return x0, y0, x0 + w, y0 + h


def center_region(img_w: int, img_h: int, aspect: float | None) -> Region:
    if not aspect:
        return 0.0, 0.0, float(img_w), float(img_h)
    if img_w / img_h > aspect:
        w = img_h * aspect
        return (img_w - w) / 2, 0.0, (img_w + w) / 2, float(img_h)
    h = img_w / aspect
    return 0.0, (img_h - h) / 2, float(img_w), (img_h + h) / 2


def crop_resize(arr: np.ndarray, region: Region, out_w: int, out_h: int, border: int = cv2.BORDER_CONSTANT) -> np.ndarray:
    """Crop `region` (may lie partly outside `arr`) and resize to out_w x out_h."""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in region)
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    pad_l, pad_t = max(0, -x0), max(0, -y0)
    pad_r, pad_b = max(0, x1 - w), max(0, y1 - h)
    crop = arr[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)]
    if pad_l or pad_t or pad_r or pad_b:
        crop = cv2.copyMakeBorder(crop, pad_t, pad_b, pad_l, pad_r, border, value=0)
    shrinking = out_w < crop.shape[1]
    return cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4)


def make_background(h: int, w: int, color: str, color2: str | None) -> np.ndarray:
    c1 = np.array(hex_to_rgb(color), np.float32)
    if not color2:
        bg = np.broadcast_to(c1, (h, w, 3)).copy()
    else:
        c2 = np.array(hex_to_rgb(color2), np.float32)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.hypot((xx / w - 0.5) / 0.5, (yy / h - 0.45) / 0.55) / 1.4142
        t = np.clip(d, 0, 1)[..., None] ** 1.6
        bg = c1 * (1 - t) + c2 * t
    rng = np.random.default_rng(7)
    bg += (rng.random((h, w, 1), dtype=np.float32) - 0.5) / 255.0  # dither against banding
    return bg.astype(np.float32)


def soften_background(rgb: np.ndarray, color: str, blur: float, desaturate: float, tint: float) -> np.ndarray:
    sigma = max(1.0, blur * max(rgb.shape[:2]))
    bg = cv2.GaussianBlur(rgb, (0, 0), sigma)
    lab = cv2.cvtColor(bg, cv2.COLOR_RGB2Lab)
    lab[..., 1:] *= 1.0 - desaturate
    bg = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)
    return (bg * (1 - tint) + np.array(hex_to_rgb(color), np.float32) * tint).astype(np.float32)


def _decontaminate(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """At soft edges, replace colour that bled in from the old background with
    the nearby subject colour (stops red-satin or green-grass fringes)."""
    inner = (alpha > 0.95).astype(np.float32)
    sigma = max(2.0, max(alpha.shape) / 400)
    num = cv2.GaussianBlur(rgb * inner[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(inner, (0, 0), sigma)[..., None]
    estimate = np.where(den > 1e-3, num / np.maximum(den, 1e-3), rgb)
    a = alpha[..., None]
    band = ((alpha > 0.02) & (alpha < 0.98))[..., None]
    return np.where(band, rgb * a + estimate * (1 - a), rgb)


def composite(fg: np.ndarray, bg: np.ndarray, alpha: np.ndarray, feather: float, shadow: float) -> np.ndarray:
    if feather > 0:
        alpha = cv2.GaussianBlur(alpha, (0, 0), feather)
    if shadow > 0:
        h, w = alpha.shape
        size = max(h, w)
        shift = np.float32([[1, 0, 0], [0, 1, 0.012 * size]])
        cast = cv2.warpAffine(alpha, shift, (w, h), borderMode=cv2.BORDER_REPLICATE)
        cast = cv2.GaussianBlur(cast, (0, 0), 0.02 * size)
        bg = bg * (1 - shadow * cast[..., None])
    fg = _decontaminate(fg, alpha)
    a = alpha[..., None]
    return np.clip(fg * a + bg * (1 - a), 0.0, 1.0).astype(np.float32)


def watermark(img: Image.Image, cfg: dict) -> Image.Image:
    text = cfg.get("text")
    if not text:
        return img
    size = max(10, round(cfg["scale"] * img.height))
    font = ImageFont.load_default(size=size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    tw, th = x1 - x0, y1 - y0
    pad = round(size * 0.8)
    pos = cfg["position"]
    x = pad if "left" in pos else (img.width - tw) // 2 if "center" in pos else img.width - tw - pad
    y = pad if "top" in pos else img.height - th - pad - y0
    rgb = tuple(round(v * 255) for v in hex_to_rgb(cfg["color"]))
    draw.text((x, y), text, font=font, fill=rgb + (round(255 * cfg["opacity"]),))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
