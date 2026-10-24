"""The processing pipeline:

  load -> subject mask -> analyse -> plan colour -> frame & crop
       -> colour / local contrast -> denoise -> sharpen -> background -> watermark
       -> analyse again -> report
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from . import compose, enhance
from .analyze import analyze_image, issues, measure, resize_long, score
from .config import load_preset, output_aspect
from .imgio import encode, open_image, to_pil
from .mask import subject_mask

# Problems that editing cannot honestly fix: they stay on the report.
UNFIXABLE = {"blurry", "low_resolution"}


@dataclass
class Result:
    image: Image.Image
    mask: Image.Image
    report: dict
    cfg: dict = field(repr=False)

    def encode(self, fmt: str | None = None, quality: int | None = None) -> bytes:
        out = self.cfg["output"]
        return encode(self.image, fmt or out["format"], quality or out["quality"])

    def renditions(self) -> list[dict]:
        """Extra sizes/formats from output.renditions, e.g. for srcset."""
        out = self.cfg["output"]
        items = []
        for r in out["renditions"]:
            img = self.image
            width = r.get("width")
            if width and width < img.width:
                img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
            fmt = r.get("format", out["format"])
            items.append({"suffix": r.get("suffix", f"-{img.width}"), "format": fmt, "width": img.width, "data": encode(img, fmt, r.get("quality", out["quality"]))})
        return items


def _output_size(cfg: dict, rw: float, rh: float) -> tuple[int, int]:
    out = cfg["output"]
    if out["width"] and out["height"]:
        return int(out["width"]), int(out["height"])
    if out["width"]:
        return int(out["width"]), max(1, round(out["width"] * rh / rw))
    if out["height"]:
        return max(1, round(out["height"] * rw / rh)), int(out["height"])
    side = out["max_side"] or max(rw, rh)
    if not out["upscale"]:
        side = min(side, max(rw, rh))
    s = side / max(rw, rh)
    return max(1, round(rw * s)), max(1, round(rh * s))


def _valid_mask(region, img_w: int, img_h: int, ow: int, oh: int) -> np.ndarray:
    x0, y0, x1, y1 = region
    xs = x0 + (np.arange(ow) + 0.5) * (x1 - x0) / ow
    ys = y0 + (np.arange(oh) + 0.5) * (y1 - y0) / oh
    return (((ys >= 0) & (ys < img_h))[:, None] & ((xs >= 0) & (xs < img_w))[None, :]).astype(np.float32)


def process(source, preset: str | None = "default", overrides: dict | None = None, cfg: dict | None = None) -> Result:
    """source: path, file object, bytes or PIL image."""
    cfg = cfg or load_preset(preset, overrides)
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    img = source if isinstance(source, Image.Image) else open_image(source)
    img = img.convert("RGB")
    W, H = img.size
    full = np.asarray(img)
    work = resize_long(full).astype(np.float32) / 255.0
    steps: list[dict] = []

    mask_w, method = subject_mask(work, cfg["mask"])
    has_subject = (mask_w > 0.5).mean() >= 0.002
    before = analyze_image(work, mask_w, cfg, (W, H))
    steps.append({"step": "mask", "method": method, "subject_found": bool(has_subject)})

    plan = enhance.plan_color(work, mask_w, cfg)

    bg_cfg = cfg["background"]
    bg_mode = bg_cfg["mode"] if has_subject else "keep"
    if bg_cfg["mode"] != "keep" and not has_subject:
        steps.append({"step": "background", "skipped": "no subject found"})
    aspect = output_aspect(cfg)
    region = None
    if cfg["framing"]["mode"] == "subject" and has_subject:
        region = compose.subject_region(mask_w, W, H, aspect, cfg["framing"]["margin"], allow_pad=bg_mode != "keep")
    if region is None:
        region = compose.center_region(W, H, aspect)
    rw, rh = region[2] - region[0], region[3] - region[1]
    ow, oh = _output_size(cfg, rw, rh)
    upscale = ow / rw
    steps.append({"step": "frame", "region": [round(v) for v in region], "output": [ow, oh], "scale": round(upscale, 3)})

    border = cv2.BORDER_REPLICATE if bg_mode == "soften" else cv2.BORDER_CONSTANT
    rgb = compose.crop_resize(full, region, ow, oh, border).astype(np.float32) / 255.0
    sx, sy = mask_w.shape[1] / W, mask_w.shape[0] / H
    mregion = (region[0] * sx, region[1] * sy, region[2] * sx, region[3] * sy)
    mask = np.clip(compose.crop_resize(mask_w, mregion, ow, oh), 0, 1) * _valid_mask(region, W, H, ow, oh)

    rgb = enhance.apply_color(rgb, plan, cfg["color"]["local_contrast"])
    steps.append({"step": "color", **plan.as_dict(), "local_contrast": cfg["color"]["local_contrast"]})

    dn = cfg["detail"]["denoise"]
    if dn == "on" or (dn == "auto" and before["noise"] > 5):
        rgb = enhance.denoise(rgb, max(before["noise"], 4.0))
        steps.append({"step": "denoise", "sigma": before["noise"]})

    sh = cfg["detail"]["sharpen"]
    amount = enhance.sharpen_amount(before["sharpness"], upscale) if sh == "auto" else 0.0 if sh == "off" else float(sh)
    if amount > 0:
        rgb = enhance.sharpen(rgb, amount)
        steps.append({"step": "sharpen", "amount": round(amount, 2)})

    if bg_mode == "replace":
        bg = compose.make_background(oh, ow, bg_cfg["color"], bg_cfg["color2"])
        rgb = compose.composite(rgb, bg, mask, bg_cfg["edge_feather"], bg_cfg["shadow"])
        steps.append({"step": "background", "mode": "replace", "color": bg_cfg["color"], "color2": bg_cfg["color2"]})
    elif bg_mode == "soften":
        s = bg_cfg["soften"]
        bg = compose.soften_background(rgb, bg_cfg["color"], s["blur"], s["desaturate"], s["tint"])
        rgb = compose.composite(rgb, bg, mask, bg_cfg["edge_feather"] * 2, 0.0)
        steps.append({"step": "background", "mode": "soften", **s})

    out_img = compose.watermark(to_pil(rgb), cfg["watermark"])

    after_metrics = measure(rgb, mask, (ow, oh))
    effective = {**after_metrics, "size": [round(rw), round(rh)]}
    after_issues = issues(effective, cfg)
    codes_after = {i["code"] for i in after_issues}
    for i in before["issues"]:
        if i["code"] in UNFIXABLE and i["code"] not in codes_after:
            after_issues.append(i)
    if upscale > 1.05:
        after_issues.append({"code": "upscaled", "severity": "info", "message": f"enlarged x{upscale:.2f} - fine detail is limited by the source"})
    after = {**after_metrics, "issues": after_issues, "score": score(after_issues)}
    codes_before = {i["code"] for i in before["issues"]}
    codes_after = {i["code"] for i in after_issues}
    report = {
        "preset": cfg["name"],
        "source": before,
        "result": after,
        "fixed": sorted(codes_before - codes_after),
        "remaining": sorted(codes_after),
        "steps": steps,
    }
    return Result(out_img, Image.fromarray((mask * 255).astype(np.uint8)), report, cfg)


def analyze(source, preset: str | None = "default", overrides: dict | None = None) -> dict:
    cfg = load_preset(preset, overrides)
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    img = source if isinstance(source, Image.Image) else open_image(source)
    full = np.asarray(img.convert("RGB"))
    work = resize_long(full).astype(np.float32) / 255.0
    mask, method = subject_mask(work, cfg["mask"])
    return {**analyze_image(work, mask, cfg, img.size), "mask_method": method}
