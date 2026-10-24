import io

import numpy as np
import pytest
from PIL import Image, ImageDraw


def make_photo(w=900, h=600, cast=(0, 0, 0), stripes=True, subject=True) -> Image.Image:
    """A skin-toned 'hand' (ellipse with dark pattern) on a busy striped background."""
    img = Image.new("RGB", (w, h), (30, 140, 120))
    d = ImageDraw.Draw(img)
    if stripes:
        for x in range(0, w, 40):
            d.rectangle([x, 0, x + 18, h], fill=(220, 40, 90) if (x // 40) % 2 else (240, 210, 40))
    if subject:
        d.ellipse([w * 0.3, h * 0.2, w * 0.7, h * 0.85], fill=(222, 170, 140))
        for i in range(12):
            cx, cy = w * 0.5, h * 0.52
            d.ellipse([cx - 10 - i * 8, cy - 10 - i * 8, cx + 10 + i * 8, cy + 10 + i * 8], outline=(110, 50, 30), width=3)
    arr = np.asarray(img).astype(np.int16) + np.array(cast, np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def to_bytes(img: Image.Image, fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, quality=92)
    return buf.getvalue()


@pytest.fixture
def photo():
    return make_photo()


HEURISTIC = {"mask": {"backend": "heuristic"}}
