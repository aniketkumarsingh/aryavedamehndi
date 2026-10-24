"""Subject masks. The AI backend (rembg) gives clean cut-outs; the heuristic
backend (skin-seeded GrabCut) needs nothing beyond OpenCV and is the fallback."""
from __future__ import annotations

import threading

import cv2
import numpy as np

_sessions: dict = {}
_lock = threading.Lock()


def ai_available() -> bool:
    try:
        import rembg  # noqa: F401
    except Exception:
        return False
    return True


def _session(model: str):
    with _lock:
        if model not in _sessions:
            from rembg import new_session

            _sessions[model] = new_session(model)
        return _sessions[model]


def _ai_mask(rgb: np.ndarray, model: str) -> np.ndarray:
    from PIL import Image
    from rembg import remove

    img = Image.fromarray((rgb * 255).astype(np.uint8))
    out = remove(img, session=_session(model), only_mask=True)
    return np.asarray(out, dtype=np.float32) / 255.0


def _heuristic_mask(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = 512 / max(h, w)
    small = cv2.resize((rgb * 255).astype(np.uint8), (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    ycc = cv2.cvtColor(small, cv2.COLOR_RGB2YCrCb)
    cr, cb = ycc[..., 1], ycc[..., 2]
    skin = ((cr >= 133) & (cr <= 180) & (cb >= 77) & (cb <= 135)).astype(np.uint8)
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    sh, sw = skin.shape
    gc = np.full((sh, sw), cv2.GC_PR_BGD, np.uint8)
    if skin.mean() > 0.01:
        gc[skin > 0] = cv2.GC_PR_FGD
        border = max(2, round(0.03 * max(sh, sw)))
        edge = np.zeros_like(skin)
        edge[:border, :] = edge[-border:, :] = 1
        edge[:, :border] = edge[:, -border:] = 1
        gc[(edge > 0) & (skin == 0)] = cv2.GC_BGD
        rect = None
        mode = cv2.GC_INIT_WITH_MASK
    else:
        rect = (round(sw * 0.1), round(sh * 0.1), round(sw * 0.8), round(sh * 0.8))
        mode = cv2.GC_INIT_WITH_RECT
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(small, gc, rect, bgd, fgd, 5, mode)
    except cv2.error:
        return skin.astype(np.float32)
    fg = np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    soft = cv2.GaussianBlur(fg.astype(np.float32), (0, 0), 1.5)
    return cv2.resize(soft, (w, h), interpolation=cv2.INTER_LINEAR)


def _clean(mask: np.ndarray, min_component: float) -> np.ndarray:
    hard = (mask > 0.5).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
    if n <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = [i + 1 for i, a in enumerate(areas) if a >= min_component * hard.size or a == areas.max()]
    keep_mask = np.isin(labels, keep).astype(np.uint8)
    keep_mask = cv2.dilate(keep_mask, np.ones((5, 5), np.uint8))
    return mask * keep_mask


def subject_mask(rgb: np.ndarray, cfg: dict) -> tuple[np.ndarray, str]:
    """rgb: float HxWx3 in [0, 1]. Returns a soft mask in [0, 1] and the method used."""
    backend = cfg["backend"]
    if backend == "none":
        return np.ones(rgb.shape[:2], np.float32), "none"
    if backend == "ai" or (backend == "auto" and ai_available()):
        if not ai_available():
            raise RuntimeError("AI masks need rembg: pip install 'image-studio[ai]'")
        mask, method = _ai_mask(rgb, cfg["model"]), f"ai:{cfg['model']}"
    elif backend in ("auto", "heuristic"):
        mask, method = _heuristic_mask(rgb), "heuristic"
    else:
        raise ValueError(f"unknown mask backend '{backend}'")
    return _clean(mask.astype(np.float32), cfg["min_component"]), method
