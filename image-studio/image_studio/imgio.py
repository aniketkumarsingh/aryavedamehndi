"""Loading and encoding. Inputs are oriented by EXIF and converted to sRGB;
outputs carry an sRGB profile and no other metadata (no GPS, no camera data)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps

MAX_PIXELS = 80_000_000
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

_SRGB = ImageCms.createProfile("sRGB")
_SRGB_BYTES = ImageCms.ImageCmsProfile(_SRGB).tobytes()

FORMATS = {
    "jpeg": ("JPEG", "image/jpeg", ".jpg"),
    "webp": ("WEBP", "image/webp", ".webp"),
    "png": ("PNG", "image/png", ".png"),
}


class ImageTooLarge(ValueError):
    pass


def open_image(source, max_pixels: int = MAX_PIXELS) -> Image.Image:
    img = Image.open(source)
    if img.width * img.height > max_pixels:
        raise ImageTooLarge(f"{img.width}x{img.height} exceeds {max_pixels} pixels")
    img = ImageOps.exif_transpose(img)
    icc = img.info.get("icc_profile")
    if icc and img.mode in ("RGB", "RGBA", "CMYK"):
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            mode = "RGBA" if img.mode == "RGBA" else "RGB"
            img = ImageCms.profileToProfile(img, src, _SRGB, outputMode=mode)
        except (ImageCms.PyCMSError, OSError):
            pass
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    return img.convert("RGB")


def to_float(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.float32) / 255.0


def to_uint8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(to_uint8(arr) if arr.dtype != np.uint8 else arr)


def normalize_format(fmt: str) -> str:
    fmt = fmt.lower().lstrip(".")
    fmt = {"jpg": "jpeg"}.get(fmt, fmt)
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}' (use jpeg, webp or png)")
    return fmt


def encode(img: Image.Image, fmt: str = "jpeg", quality: int = 88) -> bytes:
    fmt = normalize_format(fmt)
    kwargs: dict = {"icc_profile": _SRGB_BYTES}
    if fmt == "jpeg":
        kwargs.update(quality=quality, optimize=True, progressive=True, subsampling=0 if quality >= 90 else 2)
    elif fmt == "webp":
        kwargs.update(quality=quality, method=4)
    else:
        kwargs.update(optimize=True)
    buf = io.BytesIO()
    img.save(buf, FORMATS[fmt][0], **kwargs)
    return buf.getvalue()


def content_type(fmt: str) -> str:
    return FORMATS[normalize_format(fmt)][1]


def extension(fmt: str) -> str:
    return FORMATS[normalize_format(fmt)][2]


def expand_paths(paths) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        elif p.exists():
            out.append(p)
        else:
            raise FileNotFoundError(p)
    return out
