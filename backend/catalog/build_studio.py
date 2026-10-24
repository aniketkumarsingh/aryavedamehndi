"""Makes the catalog look like one shoot: runs every catalog photo through
Image Studio (image-studio/ at the repo root) and writes the results to
studio/. seed_designs.py uploads these instead of the originals.

- main photos and extra views: preset aryaveda-studio (design on the site's
  ivory backdrop, square, colour matched to reference photos)
- illustrations (designs with no photo yet): preset aryaveda-studio
- close-ups: preset aryaveda-detail (same colour look, real background)

The originals in images/, angles/ and gallery/ are never changed - they stay
the source (close-ups are cut from them by build_gallery.py). Each result is
named <original name>-u<6 hex of its content>.jpg, so a re-processed photo
gets a new URL and browsers don't keep showing a cached old version.

studio/manifest.json maps each original to its result, with the original's
checksum and the preset version; photos whose original and preset haven't
changed are skipped. Photos the report flags as blurry or low resolution are
listed at the end - editing can't fix those (see PHOTO_GUIDE.md).

Run after build_gallery.py, with Image Studio's Python:

    cd backend && ../image-studio/.venv/bin/python catalog/build_studio.py [--force]
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIO = HERE / "studio"
MANIFEST = STUDIO / "manifest.json"
MAIN_PRESET, DETAIL_PRESET = "aryaveda-studio", "aryaveda-detail"
UNFIXABLE = {"blurry", "low_resolution"}

os.environ.setdefault("IMAGE_STUDIO_PRESETS_DIR", str(HERE / "image-studio"))
try:
    from image_studio import load_preset, process
except ImportError:
    sys.exit("Image Studio isn't installed in this Python - run with ../image-studio/.venv/bin/python")


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def jobs(designs: list[dict]):
    """(folder, file, preset) for every photo designs.json shows."""
    for d in designs:
        if d.get("image"):
            yield "images", d["image"], MAIN_PRESET
        elif d.get("illustration"):
            yield "illustrations", d["illustration"]["file"], MAIN_PRESET
        for extra in d.get("more_images", []):
            yield "angles", extra["file"], MAIN_PRESET
        for closeup in d.get("closeups", []):
            yield "gallery", closeup["file"], DETAIL_PRESET


def main(force: bool) -> None:
    designs = json.loads((HERE / "designs.json").read_text())["designs"]
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    configs = {name: load_preset(name) for name in (MAIN_PRESET, DETAIL_PRESET)}
    versions = {name: checksum(json.dumps(cfg, sort_keys=True).encode()) for name, cfg in configs.items()}
    STUDIO.mkdir(exist_ok=True)

    manifest: dict = {}
    made = kept = 0
    for folder, name, preset in jobs(designs):
        src = HERE / folder / name
        if not src.exists():
            print(f"missing: {folder}/{name} - run catalog/name_images.py and catalog/build_gallery.py first")
            continue
        source = checksum(src.read_bytes())
        entry = old.get(name)
        if not force and entry and entry["source"] == source and entry["preset_version"] == versions[preset] and (STUDIO / entry["file"]).exists():
            manifest[name] = entry
            kept += 1
            continue
        result = process(src, cfg=configs[preset])
        data = result.encode(fmt="jpeg")
        out = f"{src.stem}-u{hashlib.sha256(data).hexdigest()[:6]}.jpg"
        (STUDIO / out).write_bytes(data)
        report = result.report
        manifest[name] = {
            "file": out,
            "source": source,
            "preset": preset,
            "preset_version": versions[preset],
            "score": report["result"]["score"],
            "remaining": report["remaining"],
        }
        made += 1
        print(f"{folder}/{name:22} -> studio/{out}  score {report['source']['score']} -> {report['result']['score']}")

    wanted = {e["file"] for e in manifest.values()}
    for path in STUDIO.glob("*.jpg"):
        if path.name not in wanted:
            path.unlink()
    MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=2) + "\n")
    print(f"{made} photos processed, {kept} unchanged")
    for name, e in sorted(manifest.items()):
        if UNFIXABLE & set(e["remaining"]):
            print(f"note: {name} still looks {' and '.join(sorted(UNFIXABLE & set(e['remaining'])))} - check it by eye and replace it if so")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-process every photo")
    main(parser.parse_args().force)
