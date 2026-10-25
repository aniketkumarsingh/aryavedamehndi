import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.shop import ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.models.user import User
from app.schemas.shop import (
    ShopOrderCreateIn,
    ShopOrderItemOut,
    ShopOrderOut,
    ShopPaymentOrderOut,
    ShopPaymentVerifyIn,
    ShopProductIn,
    ShopProductOut,
    ShopVariantOut,
    ShopVariantStockIn,
)
from app.services.notifications import notify
from app.services.razorpay_client import create_order, verify_payment_signature
from app.services.storage import save_upload
from app.core.time import utcnow

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
    return ShopOrderOut(
        id=order.id,
        consumer_id=order.consumer_id,
        shipping_name=order.shipping_name,
        shipping_phone=order.shipping_phone,
        shipping_address=order.shipping_address,
        total_amount=order.total_amount,
        status=order.status,
        created_at=order.created_at,
        paid_at=order.paid_at,
        shipped_at=order.shipped_at,
        items=[ShopOrderItemOut.model_validate(i) for i in items],
    )


@router.post("/orders", response_model=ShopOrderOut)
def create_order_endpoint(
    payload: ShopOrderCreateIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    order = ShopOrder(
        consumer_id=user.id,
        shipping_name=payload.shipping_name,
        shipping_phone=payload.shipping_phone,
        shipping_address=payload.shipping_address,
        total_amount=0,
        status="pending",
    )
    db.add(order)
    db.flush()

    total = 0.0
    for line in payload.items:
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
        stock_row = variant or product
        label = f"{product.name} ({variant.label})" if variant else product.name
        if stock_row.stock_quantity < line.quantity:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {stock_row.stock_quantity} left in stock for {label}")

        unit_price = stock_row.price
        subtotal = unit_price * line.quantity
        total += subtotal
        stock_row.stock_quantity -= line.quantity
        db.add(
            ShopOrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                variant_id=variant.id if variant else None,
                variant_label=variant.label if variant else None,
                unit_price=unit_price,
                quantity=line.quantity,
                subtotal=subtotal,
            )
        )

    order.total_amount = total

    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        notify(db, admin.id, "shop", "New shop order", f"₹{total} order placed by {user.name or user.phone}.", "/admin")

    db.commit()
    db.refresh(order)
    return _order_out(db, order)


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


@router.get("/orders/{order_id}", response_model=ShopOrderOut)
def get_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(ShopOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.consumer_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your order")
    return _order_out(db, order)


@router.post("/orders/{order_id}/payment/order", response_model=ShopPaymentOrderOut)
def create_shop_payment_order(order_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    order = db.get(ShopOrder, order_id)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order isn't awaiting payment")

    rp_order = create_order(order.total_amount, receipt=f"shop_{order.id}")
    order.razorpay_order_id = rp_order["id"]
    db.commit()

    return ShopPaymentOrderOut(
        order_id=order.id,
        razorpay_order_id=rp_order["id"],
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
    order = db.get(ShopOrder, order_id)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching payment order")

    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    order.razorpay_payment_id = payload.razorpay_payment_id
    order.razorpay_signature = payload.razorpay_signature
    order.status = "paid"
    order.paid_at = utcnow()
    notify(db, user.id, "shop", "Order confirmed", f"Your ₹{order.total_amount} order has been paid and will ship soon.", f"/shop/orders/{order.id}")
    db.commit()
    db.refresh(order)
    return _order_out(db, order)
