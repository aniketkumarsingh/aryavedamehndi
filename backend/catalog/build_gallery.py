"""Builds close-up detail views for every catalog design.

Each design in designs.json may list hand-picked close-ups:

    "closeups": [{"at": [cx, cy, size], "file": "bridal-01-2290.jpg"}, ...]

- cx, cy: centre of the close-up as a fraction of the photo's width/height
- size: side of the square close-up as a fraction of the photo's shorter side
- file: its name (given by catalog/name_images.py)

Close-ups are hand-picked rather than detected: on real photos, red
sarees, orange fabric and rugs look too much like henna for automatic
detection to be trusted. Crops are saved at native resolution (never
stretched; capped at MAX_OUT) to gallery/, and gallery/manifest.json
records which main photo each was cut from, so seed_designs.py can skip
close-ups of an old photo.

Re-run whenever a main image or a design's close-ups change - outputs are
rebuilt from scratch.

    cd backend && venv/bin/python catalog/build_gallery.py [slug ...]
"""

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"
GALLERY = HERE / "gallery"
MAX_OUT = 2048


def crop_box(width: int, height: int, cx: float, cy: float, size: float) -> tuple[int, int, int, int]:
    """Square box of side size * shorter side, centred on (cx, cy) and
    shifted to stay inside the photo."""
    side = round(size * min(width, height))
    left = min(max(round(cx * width - side / 2), 0), width - side)
    top = min(max(round(cy * height - side / 2), 0), height - side)
    return left, top, left + side, top + side


def build(design: dict, manifest: dict) -> int:
    """Cuts the design's close-ups; returns how many."""
    closeups = design.get("closeups", [])
    if not closeups:
        return 0
    src = IMAGES / design["image"]
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    for closeup in closeups:
        crop = img.crop(crop_box(img.width, img.height, *closeup["at"]))
        if crop.width > MAX_OUT:
            crop = crop.resize((MAX_OUT, MAX_OUT), Image.LANCZOS)
        crop.save(GALLERY / closeup["file"], quality=88, optimize=True)
        manifest[closeup["file"]] = src.name
    return len(closeups)


if __name__ == "__main__":
    only = set(sys.argv[1:])
    designs = json.loads((HERE / "designs.json").read_text())["designs"]
    GALLERY.mkdir(exist_ok=True)
    manifest_path = GALLERY / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if only and manifest_path.exists() else {}
    for d in designs:
        if only and d["slug"] not in only:
            continue
        print(f"{d['slug']:32} {build(d, manifest)} close-ups")
    # Drop close-ups no design lists any more (renamed or removed).
    wanted = {c["file"] for d in designs for c in d.get("closeups", [])}
    for path in GALLERY.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        elif path.suffix == ".jpg" and path.name not in wanted:
            path.unlink()
    manifest = {k: v for k, v in manifest.items() if k in wanted}
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n")
