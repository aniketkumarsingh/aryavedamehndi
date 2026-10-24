"""Names every catalog image <category>-<design number>-<4-digit number>.jpg,
e.g. bridal-01-4821.jpg, and records the names in designs.json.

- design number: the design's position within its category, in the order
  of designs.json (bridal-01, bridal-02, ... party-01, ...)
- 4-digit number: random, different for every image, and kept once given -
  so a file keeps its name unless its design moves to another number

designs.json then lists each design's files explicitly:

    "image": "bridal-01-4821.jpg",                     # catalog/images/
    "more_images": [{"file": "bridal-01-7305.jpg",     # catalog/angles/
                     "url": "<photo source>"}],
    "closeups": [{"at": [cx, cy, size],                # catalog/gallery/
                  "file": "bridal-01-2290.jpg"}]       # (build_gallery.py)
    "illustration": {"file": "festival-05-6614.jpg",   # catalog/illustrations/
                     "generator": "..."}               # (no photo yet)

To add a design: put its photo at catalog/images/<slug>.jpg (extra photos
in catalog/angles/<slug>/, listed in "more_images" as {"url": ...} in file
order), add it to designs.json and run this script, then build_gallery.py
and seed_designs.py. A design waiting for a photo has "photo_needed" and
no files (it still takes its design number). A replaced photo needs a new 4-digit number (delete
the old name from "image" and put the new file at images/<slug>.jpg) so
browsers don't keep showing the cached old photo.

    cd backend && venv/bin/python catalog/name_images.py [--dry-run]
"""

import json
import random
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "designs.json"
IMAGES = HERE / "images"
ANGLES = HERE / "angles"
ILLUSTRATIONS = HERE / "illustrations"
NAME = re.compile(r"^([a-z]+-\d{2})-(\d{4})\.jpg$")


def main(dry_run: bool) -> None:
    data = json.loads(CATALOG.read_text())
    designs = data["designs"]
    rng = random.SystemRandom()

    used: set[str] = set()
    for d in designs:
        for name in [d.get("image"), (d.get("illustration") or {}).get("file"), *(m.get("file") for m in d.get("more_images", [])), *(c.get("file") for c in d.get("closeups", []) if isinstance(c, dict))]:
            if name and (m := NAME.match(name)):
                if m.group(2) in used:
                    sys.exit(f"4-digit number {m.group(2)} is used twice - fix designs.json by hand")
                used.add(m.group(2))

    def fresh() -> str:
        number = rng.choice([f"{n}" for n in range(1000, 10000) if f"{n}" not in used])
        used.add(number)
        return number

    def named(prefix: str, current: str | None) -> str:
        """Keeps current's 4-digit number (with the right prefix) or gives a new one."""
        m = NAME.match(current or "")
        return f"{prefix}-{m.group(2) if m else fresh()}.jpg"

    moves: list[tuple[Path, Path]] = []
    counts: dict[str, int] = {}
    for d in designs:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
        prefix = f"{d['category']}-{counts[d['category']]:02d}"
        if d.get("photo_needed") and not d.get("image") and not (IMAGES / f"{d['slug']}.jpg").exists():
            if d.get("more_images") or d.get("closeups"):
                sys.exit(f"{d['slug']}: waiting for a photo but lists extra photos or close-ups")
            # An illustration standing in for the photo: catalog/illustrations/<slug>.jpg or its given name
            if d.get("illustration"):
                ill = d["illustration"]
                old = ILLUSTRATIONS / ill["file"] if ill.get("file") else ILLUSTRATIONS / f"{d['slug']}.jpg"
                ill["file"] = named(prefix, ill.get("file"))
                if old.name != ill["file"]:
                    if not old.exists():
                        sys.exit(f"{d['slug']}: illustration {old} not found")
                    moves.append((old, ILLUSTRATIONS / ill["file"]))
            continue

        # Main photo
        old = IMAGES / d["image"] if d.get("image") else IMAGES / f"{d['slug']}.jpg"
        d["image"] = named(prefix, d.get("image"))
        if old.name != d["image"]:
            if not old.exists():
                sys.exit(f"{d['slug']}: main photo {old} not found")
            moves.append((old, IMAGES / d["image"]))

        # Extra photos: the legacy angles/<slug>/ files pair with "more_photos" in order
        if "more_photos" in d:
            legacy = sorted((ANGLES / d["slug"]).glob("*.jpg"))
            if len(legacy) != len(d["more_photos"]):
                sys.exit(f"{d['slug']}: {len(legacy)} files in angles/{d['slug']}/ but {len(d['more_photos'])} more_photos")
            d["more_images"] = [{"src": p, "url": u} for p, u in zip(legacy, d.pop("more_photos"))]
        for extra in d.get("more_images", []):
            src = extra.pop("src", None) or ANGLES / extra["file"]
            extra["file"] = named(prefix, extra.get("file"))
            if src.name != extra["file"]:
                if not src.exists():
                    sys.exit(f"{d['slug']}: extra photo {src} not found")
                moves.append((src, ANGLES / extra["file"]))
            extra_keys = list(extra)
            for k in sorted(extra_keys, key=lambda k: k != "file"):  # "file" first
                extra[k] = extra.pop(k)

        # Close-ups are generated by build_gallery.py - just named here
        d["closeups"] = [
            {"at": list(c) if isinstance(c, list) else c["at"], "file": named(prefix, None if isinstance(c, list) else c.get("file"))}
            for c in d.get("closeups", [])
        ]

        # Keep the file names next to "photo" in the JSON
        order = list(d)
        for key in ("image", "more_images", "closeups"):
            if key in order:
                order.remove(key)
        at = order.index("photo") + 1 if "photo" in order else len(order)
        order[at:at] = [k for k in ("image", "more_images", "closeups") if k in d]
        data["designs"][designs.index(d)] = {k: d[k] for k in order}

    targets = [dst for _, dst in moves]
    if len(set(targets)) != len(targets) or any(dst.exists() for dst in targets):
        sys.exit("a new file name is taken - nothing renamed")
    for src, dst in moves:
        print(f"{src.relative_to(HERE)} -> {dst.relative_to(HERE)}")
    if dry_run:
        print(f"dry run: {len(moves)} files would be renamed")
        return
    for src, dst in moves:
        src.rename(dst)
    for folder in ANGLES.iterdir():
        if folder.is_dir() and not any(folder.iterdir()):
            shutil.rmtree(folder)
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(moves)} files renamed, designs.json updated")


if __name__ == "__main__":
    main("--dry-run" in sys.argv[1:])
