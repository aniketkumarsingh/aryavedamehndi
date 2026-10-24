"""Tone and colour. Corrections are planned on the analysis-size image and then
applied globally, so they are identical at any output size. Nothing here
recolours parts of the subject - the photo stays truthful."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .analyze import subject_stats, to_lab


@dataclass
class ColorPlan:
    da: float = 0.0
    db: float = 0.0
    gamma: float = 1.0
    contrast: float = 1.0
    pivot: float = 50.0
    chroma: float = 1.0

    def apply_lab(self, lab: np.ndarray) -> np.ndarray:
        L = lab[..., 0]
        if self.da or self.db:
            keep_white = np.clip((97.0 - L) / 15.0, 0.0, 1.0)  # leave near-white highlights neutral
            lab[..., 1] += self.da * keep_white
            lab[..., 2] += self.db * keep_white
        if self.gamma != 1.0:
            old = np.maximum(L, 1.0)
            lab[..., 0] = 100.0 * np.power(np.clip(L / 100.0, 0.0, 1.0), self.gamma)
            # Lab chroma looks weaker at higher lightness; scale it with the lift
            # so brightened photos keep their colour instead of turning milky.
            lab[..., 1:] *= np.clip(np.sqrt(lab[..., 0] / old), 0.8, 1.35)[..., None]
        if self.contrast != 1.0:
            lab[..., 0] = np.clip(self.pivot + (lab[..., 0] - self.pivot) * self.contrast, 0.0, 100.0)
        if self.chroma != 1.0:
            lab[..., 1:] *= self.chroma
        return lab

    def as_dict(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def plan_color(rgb: np.ndarray, mask: np.ndarray, cfg: dict) -> ColorPlan:
    c = cfg["color"]
    ref = c["reference"]
    lab = to_lab(rgb)
    plan = ColorPlan()
    before = subject_stats(lab, mask)

    # White balance: move the subject's anchor colour towards the reference,
    # or, without one, pull near-neutral pixels towards grey.
    limit = c["max_tint_shift"]
    if c["white_balance"] > 0:
        if ref:
            da, db = ref["a"] - before["a"], ref["b"] - before["b"]
        else:
            chroma = np.hypot(lab[..., 1], lab[..., 2])
            neutral = (chroma < 12) & (lab[..., 0] > 20) & (lab[..., 0] < 95)
            da, db = (-float(lab[..., 1][neutral].mean()), -float(lab[..., 2][neutral].mean())) if neutral.mean() > 0.03 else (0.0, 0.0)
        plan.da = _clamp(c["white_balance"] * da, -limit, limit)
        plan.db = _clamp(c["white_balance"] * db, -limit, limit)
        lab = plan.apply_lab(lab)

    # Exposure: a gamma curve on lightness that puts the subject anchor on target.
    stats = subject_stats(lab, mask)
    target = ref["L"] if ref else c["target_L"]
    if c["exposure"] > 0 and 1.0 < stats["L"] < 99.0:
        g = math.log(target / 100.0) / math.log(stats["L"] / 100.0)
        plan.gamma = _clamp(1.0 + c["exposure"] * (g - 1.0), 0.6, 1.6)
        lab = ColorPlan(gamma=plan.gamma).apply_lab(lab)
        stats = subject_stats(lab, mask)

    if ref and c["contrast"] > 0 and stats["L_std"] > 1:
        # Only ever add contrast: dense, detailed subjects legitimately have more.
        plan.contrast = _clamp((ref["L_std"] / stats["L_std"]) ** c["contrast"], 1.0, 1.25)
        plan.pivot = stats["L_median"]

    chroma = 1.0
    if ref and c["saturation"] > 0 and stats["chroma"] > 1:
        chroma = _clamp((ref["chroma"] / stats["chroma"]) ** c["saturation"], 0.92, 1.3)
    plan.chroma = chroma * (1.0 + c["vibrance"])
    return plan


def apply_color(rgb: np.ndarray, plan: ColorPlan, local_contrast: float) -> np.ndarray:
    lab = plan.apply_lab(to_lab(rgb))
    if local_contrast > 0:
        L16 = (np.clip(lab[..., 0], 0, 100) / 100.0 * 65535.0).astype(np.uint16)
        h, w = L16.shape
        tiles = max(2, round(max(h, w) / 200))
        clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(tiles, tiles))
        local = clahe.apply(L16).astype(np.float32) / 65535.0 * 100.0
        lab[..., 0] = lab[..., 0] * (1 - local_contrast) + local * local_contrast
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0.0, 1.0)


def denoise(rgb: np.ndarray, sigma: float) -> np.ndarray:
    h = float(min(10.0, max(3.0, sigma * 0.9)))
    bgr = cv2.cvtColor((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)
    out = cv2.fastNlMeansDenoisingColored(bgr, None, h, h, 7, 21)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def sharpen_amount(sharpness: float, upscale: float) -> float:
    amount = 0.6 if sharpness < 80 else 0.4 if sharpness < 200 else 0.25
    if upscale > 1.2:
        amount += 0.15
    return amount


def sharpen(rgb: np.ndarray, amount: float) -> np.ndarray:
    """Unsharp mask on luminance only, so colours don't fringe."""
    if amount <= 0:
        return rgb
    sigma = max(0.8, max(rgb.shape[:2]) / 1600.0)
    y = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    detail = y - cv2.GaussianBlur(y, (0, 0), sigma)
    detail[np.abs(detail) < 0.004] = 0.0  # don't amplify grain in flat skin
    return np.clip(rgb + amount * detail[..., None], 0.0, 1.0)
