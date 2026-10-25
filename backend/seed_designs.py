"""Loads the starter design catalog from catalog/designs.json.

Idempotent - safe to re-run, including on production:
- creates any missing category packages and applies package price updates
- creates designs that don't exist yet (matched by name, or a previous
  name in "aliases") and renames/moves/updates the category, price,
  duration, description, style, coverage and occasions of ones that do
- a design with "photo_needed" (no good photo yet) is hidden and its
  seeded photos removed; once designs.json gives it a photo it's shown
  again. A photo an admin uploaded in the app is never removed.
- images are the files designs.json names (catalog/name_images.py gives
  them, as <category>-<design number>-<4 digits>.jpg):
  - main photo: "image", in catalog/images/. Re-uploaded whenever the
    file changes.
  - gallery: "more_images" in catalog/angles/, then "closeups" in
    catalog/gallery/ (cut by catalog/build_gallery.py)
  - a design with no photo yet but an "illustration" (catalog/illustrations/,
    an AI illustration) is shown with that as its main image, labelled as an
    illustration, until a real photo replaces it
  - a design shown with an illustration may also have a realistic AI
    preview ("ai_photo", catalog/ai/) - added to its gallery as kind
    "ai_photo", labelled, and never usable as the main image
  - photos under a licence that requires credit (CC BY / BY-SA, e.g. from
    Wikimedia Commons) carry that credit - author, licence, source, and
    "edited" since the catalog versions are edited - to the site
  - each of these is uploaded as its unified version from catalog/studio/
    (catalog/build_studio.py: same backdrop and colour look for the whole
    catalog) when that is up to date with the original; otherwise the
    original is used and a note printed
- 360 view: turntable frames in catalog/spin/<slug>/ (8+ photos, named so
  they sort in rotation order: 01.jpg, 02.jpg, ...), stored as
  <category>-<design number>-360-01.jpg, ...
- every image is stored twice under its own name: a light display copy
  (<name>.jpg) and the full-resolution original for zooming
  (<name>-hd.jpg) - see app/services/storage.py save_image_variants.
  Seeded views are synced (added/removed/reordered); gallery images an
  admin uploaded by hand are never touched.
- uploads go through the normal storage path, so they land on S3 when
  that's configured

Run from backend/ after migrations:
    venv/bin/python catalog/name_images.py     # after adding a design or photo
    venv/bin/python catalog/build_gallery.py   # after changing any main image
    ../image-studio/.venv/bin/python catalog/build_studio.py   # unified versions
    venv/bin/python seed_designs.py
"""

import argparse
import hashlib
import json
from pathlib import Path

from app.database import SessionLocal
from app.models.catalog import Design, DesignImage
from app.models.package import Package
from app.services.storage import save_image_variants

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog" / "designs.json"
IMAGES = HERE / "catalog" / "images"
GALLERY = HERE / "catalog" / "gallery"
ANGLES = HERE / "catalog" / "angles"
SPIN = HERE / "catalog" / "spin"
ILLUSTRATIONS = HERE / "catalog" / "illustrations"
AI_PHOTOS = HERE / "catalog" / "ai"
STUDIO = HERE / "catalog" / "studio"
DESIGN_FIELDS = ("price_min", "price_max", "duration_minutes", "description", "style", "coverage", "occasions")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--refresh-images", action="store_true", help="re-upload every image even if unchanged")
args = parser.parse_args()

data = json.loads(CATALOG.read_text())
# close-up file -> the main photo it was cut from (catalog/build_gallery.py)
CLOSEUP_SOURCES = json.loads((GALLERY / "manifest.json").read_text()) if (GALLERY / "manifest.json").exists() else {}
# original file -> its unified version (catalog/build_studio.py)
STUDIO_FILES = json.loads((STUDIO / "manifest.json").read_text()) if (STUDIO / "manifest.json").exists() else {}
db = SessionLocal()
stats = {"packages": 0, "package_prices": 0, "designs": 0, "designs_updated": 0, "hidden": 0, "main": 0, "views_added": 0, "views_removed": 0}
warnings = []


def source_key(path: Path, prefix: str = "") -> str:
    """'<prefix><file>:<sha>' - changes whenever the file's bytes change."""
    return f"{prefix}{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}"


def shown(path: Path, slug: str) -> Path:
    """The unified version of a catalog photo when it was built from the
    original as it is now; otherwise the original."""
    entry = STUDIO_FILES.get(path.name)
    if entry and (STUDIO / entry["file"]).exists() and entry["source"] == hashlib.sha256(path.read_bytes()).hexdigest()[:12]:
        return STUDIO / entry["file"]
    warnings.append(f"{slug}: {path.name} has no up-to-date unified version - run catalog/build_studio.py")
    return path


def credit_for(photo: dict | None) -> dict | None:
    """The credit a photo's licence requires, or None (e.g. Pexels License)."""
    if not photo or not str(photo.get("license", "")).startswith("CC BY"):
        return None
    return {
        "author": photo.get("author") or "Unknown",
        "license": photo["license"],
        "license_url": photo.get("license_url"),
        "source_url": photo.get("url"),
        "edited": True,  # the catalog shows edited versions (unified backdrop, crops)
    }


def package_for(category: str) -> Package:
    pkg = (
        db.query(Package)
        .filter(Package.package_type == category, Package.is_active.is_(True))
        .order_by(Package.created_at)
        .first()
    )
    if pkg is None:
        raise SystemExit(f"No active package for category '{category}' - add it to 'packages' in {CATALOG.name}")
    return pkg


def ai_preview_views(spec: dict) -> list[dict]:
    """The design's realistic AI preview (catalog/ai/), shown in the gallery
    after the main image and labelled as AI - never a main image."""
    ai = spec.get("ai_photo")
    if not ai:
        return []
    path = AI_PHOTOS / ai["file"]
    if not path.exists():
        warnings.append(f"{spec['slug']}: {path.relative_to(HERE)} missing - skipped")
        return []
    path = shown(path, spec["slug"])
    return [{"path": path, "label": "Realistic AI preview", "kind": "ai_photo", "order": 0, "name": path.stem,
             "key": source_key(path, prefix=f"{spec['slug']}/"), "credit": {"generator": ai["generator"]}}]


def desired_gallery(spec: dict, main: Path) -> list[dict]:
    """Extra photos first, then close-ups (best first), then 360 frames."""
    slug = spec["slug"]
    views = []
    for extra in spec.get("more_images", []):
        path = ANGLES / extra["file"]
        if path.exists():
            views.append({"path": shown(path, slug), "label": "Another photo", "kind": "angle", "credit": credit_for({**spec.get("photo", {}), **extra})})
        else:
            warnings.append(f"{slug}: {path.relative_to(HERE)} missing - skipped")
    for i, closeup in enumerate(spec.get("closeups", []), start=1):
        path = GALLERY / closeup["file"]
        if not path.exists() or CLOSEUP_SOURCES.get(path.name) != main.name:
            warnings.append(f"{slug}: close-up {path.name} not built from {main.name} - re-run catalog/build_gallery.py")
            continue
        views.append({"path": shown(path, slug), "label": f"Close-up {i}", "kind": "detail", "credit": credit_for(spec.get("photo"))})
    prefix = main.stem.rsplit("-", 1)[0]
    spin_dir = SPIN / slug
    frames = sorted(p for p in spin_dir.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if spin_dir.is_dir() else []
    if frames and len(frames) < 8:
        warnings.append(f"{slug}: only {len(frames)} 360 frames - need at least 8, skipped")
        frames = []
    for i, frame in enumerate(frames, start=1):
        views.append({"path": frame, "label": f"Frame {i}", "kind": "spin", "name": f"{prefix}-360-{i:02d}"})
    for order, view in enumerate(views):
        view["order"] = order
        view.setdefault("name", view["path"].stem)
        view["key"] = source_key(view["path"], prefix=f"{slug}/")
    return views


def sync_gallery(design: Design, views: list[dict]) -> None:
    seeded = {img.source_key: img for img in db.query(DesignImage).filter(DesignImage.design_id == design.id, DesignImage.source_key.isnot(None))}
    wanted = {v["key"] for v in views}
    for key, img in seeded.items():
        if key not in wanted or args.refresh_images:
            db.delete(img)
            stats["views_removed"] += 1
    for v in views:
        img = None if args.refresh_images else seeded.get(v["key"])
        if img is None:
            url, hd_url = save_image_variants(v["path"].read_bytes(), "catalog", name=v["name"])
            db.add(DesignImage(design_id=design.id, url=url, hd_url=hd_url, label=v["label"], kind=v["kind"], sort_order=v["order"], source_key=v["key"], credit=v.get("credit")))
            stats["views_added"] += 1
        else:
            img.label, img.kind, img.sort_order, img.credit = v["label"], v["kind"], v["order"], v.get("credit")


for spec in data["packages"]:
    if db.query(Package).filter(Package.package_type == spec["package_type"]).first() is None:
        db.add(Package(**spec, negotiable=True))
        stats["packages"] += 1
db.flush()

for spec in data["package_updates"]:
    pkg = package_for(spec["package_type"])
    for key in ("name", "description", "price_min", "price_max"):
        if key in spec and getattr(pkg, key) != spec[key]:
            setattr(pkg, key, spec[key])
            stats["package_prices"] += 1

for order, spec in enumerate(data["designs"]):
    slug = spec["slug"]
    pkg = package_for(spec["category"])
    # Matched by current name, or a previous one listed in "aliases" - so a
    # renamed design is updated in place (keeping its artist links and
    # bookings) rather than duplicated.
    names = [spec["name"], *spec.get("aliases", [])]
    matches = db.query(Design).filter(Design.name.in_(names)).all()
    if len(matches) > 1:
        raise SystemExit(f"{slug}: several designs are named {names} - merge them by hand first")
    design = matches[0] if matches else None
    if design is not None and (design.name, design.package_id, design.sort_order) != (spec["name"], pkg.id, order):
        design.name, design.package_id, design.sort_order = spec["name"], pkg.id, order
        stats["designs_updated"] += 1
    created = design is None
    if created:
        design = Design(package_id=pkg.id, name=spec["name"], sort_order=order, is_active=False, **{k: spec[k] for k in DESIGN_FIELDS})
        db.add(design)
        db.flush()
        stats["designs"] += 1
    elif any(getattr(design, k) != spec[k] for k in DESIGN_FIELDS):
        for k in DESIGN_FIELDS:
            setattr(design, k, spec[k])
        stats["designs_updated"] += 1

    main = IMAGES / spec["image"] if spec.get("image") else None
    illustration = ILLUSTRATIONS / spec["illustration"]["file"] if main is None and spec.get("illustration") else None
    admin_photo = design.image_url and design.image_source is None
    if illustration is not None and illustration.exists():
        # Shown with a labelled illustration until a real photo arrives; the
        # photo it still needs stays recorded for the admin.
        if not admin_photo or args.refresh_images:
            if created or design.image_url is None:
                design.is_active = True
            design.photo_needed = spec.get("photo_needed")
            photo = shown(illustration, slug)
            key = source_key(photo, prefix=f"{slug}/")
            if design.image_source != key or args.refresh_images:
                design.image_url, design.image_hd_url = save_image_variants(photo.read_bytes(), "catalog", name=photo.stem)
                design.image_source = key
                stats["main"] += 1
            design.image_kind = "illustration"
            design.image_credit = {"generator": spec["illustration"]["generator"]}
            sync_gallery(design, ai_preview_views(spec))
    elif main is None and spec.get("photo_needed"):
        # Hidden until it has a good photo - unless an admin already gave it one.
        if not admin_photo:
            if design.is_active or design.image_url or design.photo_needed != spec["photo_needed"]:
                stats["hidden"] += 1
            design.image_url = design.image_hd_url = design.image_source = design.image_credit = None
            design.image_kind = "photo"
            design.photo_needed, design.is_active = spec["photo_needed"], False
            sync_gallery(design, [])
    elif main is None or not main.exists():
        warnings.append(f"{slug}: no main photo yet - run catalog/name_images.py")
    else:
        # Shown once it has a photo - but a design an admin switched off stays off.
        if design.photo_needed is not None or created:
            design.photo_needed, design.is_active = None, True
        photo = shown(main, slug)
        key = source_key(photo, prefix=f"{slug}/")
        # A main photo an admin uploaded (image_source is null but there
        # is an image) is left alone unless --refresh-images.
        admin_owned = design.image_url and design.image_source is None and not args.refresh_images
        if not admin_owned and (design.image_source != key or args.refresh_images):
            design.image_url, design.image_hd_url = save_image_variants(photo.read_bytes(), "catalog", name=photo.stem)
            design.image_source = key
            stats["main"] += 1
        if not admin_owned:
            design.image_kind, design.image_credit = "photo", credit_for(spec.get("photo"))
        sync_gallery(design, desired_gallery(spec, main))

db.commit()
print(f"packages: {stats['packages']} created, {stats['package_prices']} fields updated")
print(f"designs:  {stats['designs']} created, {stats['designs_updated']} updated, {stats['hidden']} hidden (photo needed), {stats['main']} main photos uploaded")
print(f"gallery:  {stats['views_added']} views added, {stats['views_removed']} removed")
for w in warnings:
    print("note:", w)
