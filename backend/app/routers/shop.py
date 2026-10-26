import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.payment_ops import Refund
from app.models.shop import ShopCoupon, ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.models.user import User
from app.schemas.shop import (
    ShopCheckoutConfigOut,
    ShopCouponIn,
    ShopCouponOut,
    ShopOrderCancelIn,
    ShopOrderCreateIn,
    ShopOrderItemIn,
    ShopOrderItemOut,
    ShopOrderOut,
    ShopPaymentOrderOut,
    ShopPaymentVerifyIn,
    ShopProductIn,
    ShopProductOut,
    ShopQuoteIn,
    ShopQuoteOut,
    ShopRefundOut,
    ShopVariantOut,
    ShopVariantStockIn,
)
from app.services import idempotency, pdf
from app.services.documents import credit_note_document, order_document
from app.services.notifications import notify_admins
from app.services.platform_settings import get_platform_settings
from app.services.razorpay_client import create_order, verify_payment_signature
from app.services.shop_orders import cancel_order, cod_problem, confirm_cod, coupon_problem, is_stale, normalise_code, price_order, release_stale_orders, settle_payment
from app.services.storage import save_upload

router = APIRouter(prefix="/shop", tags=["shop"])
settings = get_settings()


# -------------------------------------------------------------- products --

def _public_out(product: ShopProduct) -> ShopProductOut:
    """Shoppers see active variants only, and never the licence number field
    (it's printed on the pack, not needed in the API)."""
    out = ShopProductOut.model_validate(product)
    out.variants = [v for v in out.variants if v.is_active]
    out.licence_number = None
    return out


def _sort_key(p: ShopProduct):
    return (p.sort_order or 0, -(p.created_at.timestamp() if p.created_at else 0))


def _publish_block(product: ShopProduct) -> str | None:
    if product.requires_licence and not (product.licence_number or "").strip():
        return f"{product.name} needs its manufacturing licence number (AYUSH or cosmetic) before it can be sold"
    if product.variants and not any(v.is_active for v in product.variants):
        return f"{product.name} has no active pack sizes"
    return None


@router.get("/products", response_model=list[ShopProductOut])
def list_products(category: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ShopProduct).filter(ShopProduct.is_active.is_(True))
    if category:
        q = q.filter(ShopProduct.category == category)
    return [_public_out(p) for p in sorted(q.all(), key=_sort_key)]


@router.get("/admin/products", response_model=list[ShopProductOut], dependencies=[Depends(require_role("admin"))])
def list_all_products(db: Session = Depends(get_db)):
    """Every product, drafts included, for the admin shop tab."""
    return sorted(db.query(ShopProduct).all(), key=_sort_key)


@router.get("/products/{product_id}", response_model=ShopProductOut)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return _public_out(product)


@router.get("/products/by-slug/{slug}", response_model=ShopProductOut)
def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    product = db.query(ShopProduct).filter(ShopProduct.slug == slug, ShopProduct.is_active.is_(True)).first()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return _public_out(product)


@router.get("/feed.csv", response_class=Response)
def product_feed(db: Session = Depends(get_db)):
    """Catalogue feed for Meta (Facebook/Instagram) Commerce Manager and
    Google Merchant Center: one row per live pack size, grouped by product,
    so ads can show the right product and price. Point the ad platform's
    scheduled feed at this URL."""
    site = settings.public_site_url.rstrip("/")
    api = settings.public_api_url.rstrip("/")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "item_group_id", "title", "description", "availability", "condition", "price", "link", "image_link", "brand", "product_type", "size"])
    for product in sorted(db.query(ShopProduct).filter(ShopProduct.is_active.is_(True), ShopProduct.slug.isnot(None)).all(), key=_sort_key):
        image = next((u for u in (product.image_urls or "").split(",") if u), "")
        if image.startswith("/"):
            image = api + image
        rows = [v for v in product.variants if v.is_active] or [None]
        for v in rows:
            stock = v.stock_quantity if v else product.stock_quantity
            writer.writerow([
                f"{product.slug}-{v.id.hex[:8]}" if v else product.slug,
                product.slug,
                f"{product.name} - {v.label}" if v and len(rows) > 1 else product.name,
                product.description or product.name,
                "in stock" if stock > 0 else "out of stock",
                "new",
                f"{(v.price if v else product.price):.2f} INR",
                f"{site}/shop/{product.slug}",
                image,
                "AryaVeda Mehndi",
                product.category or "",
                v.label if v else "",
            ])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")


@router.post("/products", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def create_product(payload: ShopProductIn, db: Session = Depends(get_db)):
    product = ShopProduct(**payload.model_dump())
    # A licensed product starts as a draft until its licence number is in.
    product.is_active = _publish_block(product) is None
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def update_product(product_id: uuid.UUID, payload: ShopProductIn, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    # Only fields the admin sent, so a short edit form can't blank the details.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    if product.is_active and (reason := _publish_block(product)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/publish", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def publish_product(product_id: uuid.UUID, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if reason := _publish_block(product):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)
    product.is_active = True
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
def deactivate_product(product_id: uuid.UUID, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product.is_active = False
    db.commit()


@router.put("/variants/{variant_id}/stock", response_model=ShopVariantOut, dependencies=[Depends(require_role("admin"))])
def set_variant_stock(variant_id: uuid.UUID, payload: ShopVariantStockIn, db: Session = Depends(get_db)):
    variant = db.get(ShopProductVariant, variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pack size not found")
    variant.stock_quantity = payload.stock_quantity
    db.commit()
    db.refresh(variant)
    return variant


@router.post("/products/{product_id}/image", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
async def upload_product_image(product_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    content = await file.read()
    url = save_upload(content, "shop")
    existing = [u for u in (product.image_urls or "").split(",") if u]
    if product.image_kind == "illustrative":
        # A real photo replaces the illustrative image rather than sitting beside it.
        existing = []
        product.image_kind = "photo"
        product.image_source = None
    existing.append(url)
    product.image_urls = ",".join(existing)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}/image", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def remove_product_image(product_id: uuid.UUID, url: str, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    remaining = [u for u in (product.image_urls or "").split(",") if u and u != url]
    product.image_urls = ",".join(remaining)
    db.commit()
    db.refresh(product)
    return product


# ---------------------------------------------------------------- orders --

def _order_out(db: Session, order: ShopOrder) -> ShopOrderOut:
    items = db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id).all()
    refunds = (
        db.query(Refund)
        .filter(Refund.target_type == "shop_order", Refund.target_id == order.id)
        .order_by(Refund.created_at)
        .all()
    )
    fields = {f: getattr(order, f) for f in ShopOrderOut.model_fields if f not in ("items", "refunds")}
    return ShopOrderOut(
        **fields,
        items=[ShopOrderItemOut.model_validate(i) for i in items],
        refunds=[ShopRefundOut.model_validate(r) for r in refunds],
    )


def _priced_lines(db: Session, lines: list[ShopOrderItemIn], lock: bool = False) -> list[dict]:
    """Resolves each cart line to its product, pack size and unit price,
    rejecting hidden products and missing/retired pack sizes. With `lock`,
    the stock rows are locked (in a fixed order, so concurrent checkouts
    can't deadlock) until the transaction ends."""
    priced = []
    for line in lines:
        product = db.get(ShopProduct, line.product_id)
        if product is None or not product.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {line.product_id} not found")
        active_variants = [v for v in product.variants if v.is_active]
        variant = None
        if active_variants:
            variant = next((v for v in active_variants if v.id == line.variant_id), None)
            if variant is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose a pack size for {product.name}")
        elif line.variant_id is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{product.name} has no pack sizes")
        priced.append({
            "product": product,
            "variant": variant,
            "stock_row": variant or product,
            "label": f"{product.name} ({variant.label})" if variant else product.name,
            "unit_price": (variant or product).price,
            "quantity": line.quantity,
        })
    if lock:
        for line in sorted(priced, key=lambda l: (type(l["stock_row"]).__name__, str(l["stock_row"].id))):
            line["stock_row"] = db.get(type(line["stock_row"]), line["stock_row"].id, with_for_update=True, populate_existing=True)
    return priced


def _coupon_for(db: Session, code: str | None, user: User, items_amount: float) -> ShopCoupon | None:
    if not code or not code.strip():
        return None
    coupon = db.query(ShopCoupon).filter(ShopCoupon.code == normalise_code(code)).first()
    if problem := coupon_problem(db, coupon, user.id, items_amount):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    return coupon


@router.get("/checkout-config", response_model=ShopCheckoutConfigOut)
def checkout_config(db: Session = Depends(get_db)):
    s = get_platform_settings(db)
    return ShopCheckoutConfigOut(
        shipping_fee=s["shop_shipping_fee"],
        free_shipping_above=s["shop_free_shipping_above"],
        payment_window_minutes=s["shop_payment_window_minutes"],
        cod_enabled=s["shop_cod_enabled"],
        cod_max_order=s["shop_cod_max_order"],
        cod_fee=s["shop_cod_fee"],
    )


@router.post("/quote", response_model=ShopQuoteOut)
def quote(payload: ShopQuoteIn, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    """Prices the cart for the chosen payment method without placing an
    order. A bad coupon or unavailable COD doesn't fail the quote - the
    reasons come back in coupon_error / cod_error."""
    lines = _priced_lines(db, payload.items)
    items_amount = sum(line["unit_price"] * line["quantity"] for line in lines)
    coupon, error = None, None
    if payload.coupon_code and payload.coupon_code.strip():
        coupon = db.query(ShopCoupon).filter(ShopCoupon.code == normalise_code(payload.coupon_code)).first()
        if error := coupon_problem(db, coupon, user.id, items_amount):
            coupon = None
    online = price_order(db, items_amount, coupon, "online")
    cod_error = cod_problem(db, user.id, online["total_amount"])
    method = payload.payment_method if not (payload.payment_method == "cod" and cod_error) else "online"
    price = price_order(db, items_amount, coupon, method)
    return ShopQuoteOut(**price, coupon_code=coupon.code if coupon else None, coupon_error=error,
                        cod_available=cod_error is None, cod_error=cod_error)


@router.post("/orders", response_model=ShopOrderOut)
def create_order_endpoint(
    payload: ShopOrderCreateIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Places an order. Send an Idempotency-Key header (a fresh UUID per
    checkout attempt): a retried or double-tapped request then returns the
    same order instead of placing a second one."""
    if idempotency_key:
        if replay := idempotency.claim(db, user.id, "shop.create_order", idempotency_key, payload.model_dump(mode="json")):
            return replay
    try:
        return _place_order(db, payload, user, idempotency_key)
    except HTTPException:
        # Nothing was placed: release the key (and any locks) so a corrected
        # retry can run.
        db.rollback()
        raise


def _place_order(db: Session, payload: ShopOrderCreateIn, user: User, idempotency_key: str | None) -> ShopOrderOut:
    lines = _priced_lines(db, payload.items, lock=True)
    if any(line["stock_row"].stock_quantity < line["quantity"] for line in lines):
        # Abandoned checkouts may still hold the stock until the scheduled
        # release runs - free any that are past their window, then recheck.
        if release_stale_orders(db):
            db.flush()
            for line in lines:
                db.refresh(line["stock_row"])
    for line in lines:
        if line["stock_row"].stock_quantity < line["quantity"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {line['stock_row'].stock_quantity} left in stock for {line['label']}")
    items_amount = sum(line["unit_price"] * line["quantity"] for line in lines)
    coupon = _coupon_for(db, payload.coupon_code, user, items_amount)
    if payload.payment_method == "cod":
        if problem := cod_problem(db, user.id, price_order(db, items_amount, coupon, "online")["total_amount"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    price = price_order(db, items_amount, coupon, payload.payment_method)

    order = ShopOrder(
        consumer_id=user.id,
        shipping_name=payload.shipping_name,
        shipping_phone=payload.shipping_phone,
        shipping_address=payload.shipping_address,
        shipping_state=payload.shipping_state,
        shipping_pincode=payload.shipping_pincode,
        contact_email=payload.contact_email,
        payment_method=payload.payment_method,
        payment_status="unpaid",
        items_amount=price["items_amount"],
        discount_amount=price["discount_amount"],
        shipping_fee=price["shipping_fee"],
        cod_fee=price["cod_fee"],
        total_amount=price["total_amount"],
        coupon_code=coupon.code if coupon else None,
        status="pending",
    )
    db.add(order)
    db.flush()

    for line in lines:
        variant = line["variant"]
        line["stock_row"].stock_quantity -= line["quantity"]
        db.add(
            ShopOrderItem(
                order_id=order.id,
                product_id=line["product"].id,
                product_name=line["product"].name,
                variant_id=variant.id if variant else None,
                variant_label=variant.label if variant else None,
                hsn_code=line["product"].hsn_code,
                gst_rate=line["product"].gst_rate,
                unit_price=line["unit_price"],
                quantity=line["quantity"],
                subtotal=line["unit_price"] * line["quantity"],
            )
        )
    if payload.payment_method == "cod":
        confirm_cod(db, order)

    method = "Cash on Delivery" if payload.payment_method == "cod" else "online payment pending"
    notify_admins(db, "New shop order", f"₹{order.total_amount:g} order ({method}) placed by {user.name or user.phone}.", "/admin")

    db.flush()
    out = _order_out(db, order)
    if idempotency_key:
        idempotency.store(db, user.id, "shop.create_order", idempotency_key, 200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/orders", response_model=list[ShopOrderOut])
def list_my_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    orders = (
        db.query(ShopOrder)
        .filter(ShopOrder.consumer_id == user.id)
        .order_by(ShopOrder.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_order_out(db, o) for o in orders]


def _visible_order(db: Session, order_id: uuid.UUID, user: User) -> ShopOrder:
    order = db.get(ShopOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.consumer_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your order")
    return order


@router.get("/orders/{order_id}", response_model=ShopOrderOut)
def get_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _order_out(db, _visible_order(db, order_id, user))


@router.get("/orders/{order_id}/document")
def order_document_json(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The order's receipt, or its GST invoice once dispatched, as data."""
    order = _visible_order(db, order_id, user)
    if order.status == "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A receipt is available once the order is confirmed")
    return order_document(db, order)


@router.get("/orders/{order_id}/document.pdf")
def order_document_pdf(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = _visible_order(db, order_id, user)
    if order.status == "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A receipt is available once the order is confirmed")
    doc = order_document(db, order)
    return Response(pdf.render(doc), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc["number"].replace(" ", "-")}.pdf"'})


@router.get("/refunds/{refund_id}/credit-note")
def credit_note_json(refund_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refund, order = _credit_note_or_404(db, refund_id, user)
    return credit_note_document(db, refund, order)


@router.get("/refunds/{refund_id}/credit-note.pdf")
def credit_note_pdf(refund_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refund, order = _credit_note_or_404(db, refund_id, user)
    return Response(pdf.render(credit_note_document(db, refund, order)), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{refund.credit_note_number}.pdf"'})


def _credit_note_or_404(db: Session, refund_id: uuid.UUID, user: User) -> tuple[Refund, ShopOrder]:
    refund = db.get(Refund, refund_id)
    if refund is None or refund.target_type != "shop_order" or not refund.credit_note_number:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credit note not found")
    return refund, _visible_order(db, refund.target_id, user)


@router.post("/orders/{order_id}/payment/order", response_model=ShopPaymentOrderOut)
def create_shop_payment_order(order_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    order = db.get(ShopOrder, order_id)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.payment_method != "online":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order is Cash on Delivery")
    if order.status == "pending" and is_stale(db, order):
        cancel_order(db, order, "Payment not completed in time")
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order expired before payment - please place it again")
    if order.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order isn't awaiting payment")

    # A retry ("Pay now") reuses the order's Razorpay order, so a payment on
    # any attempt still matches this order (in verify and in the webhook).
    if not order.razorpay_order_id:
        order.razorpay_order_id = create_order(order.total_amount, receipt=f"shop_{order.id}")["id"]
        db.commit()

    return ShopPaymentOrderOut(
        order_id=order.id,
        razorpay_order_id=order.razorpay_order_id,
        razorpay_key_id=settings.razorpay_key_id or "dev_mode_no_key",
        amount=order.total_amount,
        currency="INR",
    )


@router.post("/orders/{order_id}/payment/verify", response_model=ShopOrderOut)
def verify_shop_payment(
    order_id: uuid.UUID,
    payload: ShopPaymentVerifyIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    order = db.get(ShopOrder, order_id, with_for_update=True)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching payment order")

    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")
    outcome = settle_payment(db, order, payload.razorpay_payment_id, payload.razorpay_signature)
    db.commit()
    if outcome == "refunded":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order had expired, so your payment is being refunded - please order again")
    db.refresh(order)
    return _order_out(db, order)


@router.post("/orders/{order_id}/cancel", response_model=ShopOrderOut)
def cancel_my_order(
    order_id: uuid.UUID,
    payload: ShopOrderCancelIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    """A customer can cancel until the order ships; money paid online is refunded."""
    order = db.get(ShopOrder, order_id, with_for_update=True)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status not in ("pending", "confirmed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order can no longer be cancelled")
    cancel_order(db, order, payload.reason or "Cancelled by customer", initiated_by=user.id)
    notify_admins(db, "Shop order cancelled", f"₹{order.total_amount:g} order cancelled by the customer.", "/admin")
    db.commit()
    db.refresh(order)
    return _order_out(db, order)


# --------------------------------------------------------------- coupons --

def _coupon_out(db: Session, coupon: ShopCoupon) -> ShopCouponOut:
    out = ShopCouponOut.model_validate(coupon)
    out.uses = db.query(ShopOrder).filter(ShopOrder.coupon_code == coupon.code, ShopOrder.status != "cancelled").count()
    return out


@router.get("/admin/coupons", response_model=list[ShopCouponOut], dependencies=[Depends(require_role("admin"))])
def list_coupons(db: Session = Depends(get_db)):
    return [_coupon_out(db, c) for c in db.query(ShopCoupon).order_by(ShopCoupon.created_at.desc()).all()]


def _check_dates(payload: ShopCouponIn) -> None:
    if payload.starts_at and payload.expires_at and payload.expires_at <= payload.starts_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The coupon must expire after it starts")


@router.post("/admin/coupons", response_model=ShopCouponOut, dependencies=[Depends(require_role("admin"))])
def create_coupon(payload: ShopCouponIn, db: Session = Depends(get_db)):
    _check_dates(payload)
    code = normalise_code(payload.code)
    if db.query(ShopCoupon).filter(ShopCoupon.code == code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Coupon {code} already exists")
    coupon = ShopCoupon(**{**payload.model_dump(), "code": code})
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return _coupon_out(db, coupon)


@router.put("/admin/coupons/{coupon_id}", response_model=ShopCouponOut, dependencies=[Depends(require_role("admin"))])
def update_coupon(coupon_id: uuid.UUID, payload: ShopCouponIn, db: Session = Depends(get_db)):
    """Everything but the code can change (orders reference the code)."""
    coupon = db.get(ShopCoupon, coupon_id)
    if coupon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coupon not found")
    _check_dates(payload)
    for field, value in payload.model_dump(exclude={"code"}).items():
        setattr(coupon, field, value)
    db.commit()
    db.refresh(coupon)
    return _coupon_out(db, coupon)
