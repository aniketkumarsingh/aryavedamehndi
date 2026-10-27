"""Seed the shop catalogue from shop/products.json.

    python seed_shop.py

Idempotent, keyed by product slug:
- New products are created as drafts (hidden). An admin publishes each one
  from the admin Shop tab; products that need a manufacturing licence can't
  be published until their licence number is entered.
- Existing products get their details, categories and pack-size prices synced,
  but their published/draft state, licence number and stock are never touched.
- Pack sizes are matched by label; ones dropped from the JSON are deactivated.
- Each product's image comes from shop/images/<slug>.jpg and is marked
  "illustrative" (AI-made, labelled on the site). Once an admin uploads a real
  photo the seed leaves the images alone.
"""
import hashlib
import json
from pathlib import Path

from app.database import SessionLocal
from app.models.shop import SHOP_CATEGORIES, ShopProduct, ShopProductVariant
from app.services.storage import save_upload

HERE = Path(__file__).parent / "shop"
DETAIL_FIELDS = ("name", "category", "description", "ingredients", "how_to_use", "safety_notes", "shelf_life", "storage", "requires_licence")

data = json.loads((HERE / "products.json").read_text())
db = SessionLocal()
stats = {"created": 0, "updated": 0, "variants_added": 0, "variants_retired": 0, "images": 0, "no_image": []}

for order, spec in enumerate(data["products"]):
    assert spec["category"] in SHOP_CATEGORIES, spec["slug"]
    product = db.query(ShopProduct).filter(ShopProduct.slug == spec["slug"]).first()
    if product is None:
        # Henna, hair and skin products: returns only if damaged or wrong
        # (refund policy); set once, then it's the admin's to change.
        product = ShopProduct(slug=spec["slug"], is_active=False, stock_quantity=0, price=0,
                              returnable=spec.get("returnable", spec["category"] not in ("body-art", "hair", "skin")))
        db.add(product)
        stats["created"] += 1
    changed = False
    for field in DETAIL_FIELDS:
        if getattr(product, field) != spec[field]:
            setattr(product, field, spec[field])
            changed = True
    if product.sort_order != order:
        product.sort_order = order
        changed = True

    by_label = {v.label: v for v in product.variants}
    for i, (label, price) in enumerate(spec["variants"]):
        variant = by_label.pop(label, None)
        if variant is None:
            product.variants.append(ShopProductVariant(label=label, price=price, stock_quantity=0, sort_order=i, is_active=True))
            stats["variants_added"] += 1
        elif (variant.price, variant.sort_order, variant.is_active) != (price, i, True):
            variant.price, variant.sort_order, variant.is_active = price, i, True
            changed = True
    for variant in by_label.values():
        if variant.is_active:
            variant.is_active = False
            stats["variants_retired"] += 1
    # The product's own price is the "from" price shown on the card.
    low = min(price for _, price in spec["variants"])
    if product.price != low:
        product.price = low
        changed = True

    image = HERE / "images" / f"{spec['slug']}.jpg"
    admin_photo = product.image_kind == "photo" and product.image_urls
    if not image.exists():
        stats["no_image"].append(spec["slug"])
    elif not admin_photo:
        key = f"{image.name}:{hashlib.sha256(image.read_bytes()).hexdigest()[:12]}"
        if product.image_source != key:
            product.image_urls = save_upload(image.read_bytes(), "shop", name=f"{spec['slug']}-{key[-6:]}")
            product.image_kind, product.image_source = "illustrative", key
            stats["images"] += 1
    if changed and product.id is not None:
        stats["updated"] += 1

db.commit()
print(f"products: {stats['created']} created (as drafts), {stats['updated']} updated")
print(f"pack sizes: {stats['variants_added']} added, {stats['variants_retired']} retired")
print(f"images: {stats['images']} uploaded" + (f", missing for {len(stats['no_image'])}: {', '.join(stats['no_image'])}" if stats["no_image"] else ""))
