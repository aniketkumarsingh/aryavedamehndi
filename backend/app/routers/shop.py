import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.shop import ShopOrder, ShopOrderItem, ShopProduct
from app.models.user import User
from app.schemas.shop import (
    ShopOrderCreateIn,
    ShopOrderItemOut,
    ShopOrderOut,
    ShopPaymentOrderOut,
    ShopPaymentVerifyIn,
    ShopProductIn,
    ShopProductOut,
)
from app.services.notifications import notify
from app.services.razorpay_client import create_order, verify_payment_signature
from app.services.storage import save_upload
from app.core.time import utcnow

router = APIRouter(prefix="/shop", tags=["shop"])
settings = get_settings()


# -------------------------------------------------------------- products --

@router.get("/products", response_model=list[ShopProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(ShopProduct).filter(ShopProduct.is_active.is_(True)).order_by(ShopProduct.created_at.desc()).all()


@router.get("/products/{product_id}", response_model=ShopProductOut)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.post("/products", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def create_product(payload: ShopProductIn, db: Session = Depends(get_db)):
    product = ShopProduct(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
def update_product(product_id: uuid.UUID, payload: ShopProductIn, db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    for field, value in payload.model_dump().items():
        setattr(product, field, value)
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


@router.post("/products/{product_id}/image", response_model=ShopProductOut, dependencies=[Depends(require_role("admin"))])
async def upload_product_image(product_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    product = db.get(ShopProduct, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    content = await file.read()
    url = save_upload(content, "shop")
    existing = [u for u in (product.image_urls or "").split(",") if u]
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
        if product.stock_quantity < line.quantity:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Only {product.stock_quantity} left in stock for {product.name}")

        subtotal = product.price * line.quantity
        total += subtotal
        product.stock_quantity -= line.quantity
        db.add(
            ShopOrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                unit_price=product.price,
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
