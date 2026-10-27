import uuid
from datetime import datetime, timezone

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.shop import SHOP_ORDER_STATUSES


class ShopProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    price: float = Field(gt=0, le=100_000)
    stock_quantity: int = Field(ge=0, le=100_000, default=0)
    category: Literal["body-art", "hair", "skin", "traditional", "tools", "learn", "decor", "gifts"] | None = None
    ingredients: str | None = Field(default=None, max_length=2000)
    how_to_use: str | None = Field(default=None, max_length=2000)
    safety_notes: str | None = Field(default=None, max_length=2000)
    shelf_life: str | None = Field(default=None, max_length=120)
    storage: str | None = Field(default=None, max_length=200)
    requires_licence: bool = False
    licence_number: str | None = Field(default=None, max_length=80)
    hsn_code: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    gst_rate: float | None = Field(default=None, ge=0, le=40)
    weight_g: int | None = Field(default=None, ge=1, le=50_000)
    length_cm: float | None = Field(default=None, gt=0, le=200)
    breadth_cm: float | None = Field(default=None, gt=0, le=200)
    height_cm: float | None = Field(default=None, gt=0, le=200)
    returnable: bool | None = None


class PackageSizeIn(BaseModel):
    """Packed size of one unit, for courier bookings."""

    weight_g: int = Field(ge=1, le=50_000)
    length_cm: float | None = Field(default=None, gt=0, le=200)
    breadth_cm: float | None = Field(default=None, gt=0, le=200)
    height_cm: float | None = Field(default=None, gt=0, le=200)


class ShopVariantOut(BaseModel):
    id: uuid.UUID
    label: str
    price: float
    stock_quantity: int
    sort_order: int
    is_active: bool
    weight_g: int | None = None
    length_cm: float | None = None
    breadth_cm: float | None = None
    height_cm: float | None = None

    class Config:
        from_attributes = True


class ShopVariantStockIn(BaseModel):
    stock_quantity: int = Field(ge=0, le=100_000)


class ShopProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: float
    stock_quantity: int
    image_urls: str | None
    is_active: bool
    created_at: datetime
    slug: str | None = None
    category: str | None = None
    ingredients: str | None = None
    how_to_use: str | None = None
    safety_notes: str | None = None
    shelf_life: str | None = None
    storage: str | None = None
    requires_licence: bool = False
    licence_number: str | None = None
    # "photo" or "illustrative" (AI image, shown labelled)
    image_kind: str = "photo"
    hsn_code: str | None = None
    gst_rate: float | None = None
    returnable: bool = True
    rating_avg: float = 0
    rating_count: int = 0
    weight_g: int | None = None
    length_cm: float | None = None
    breadth_cm: float | None = None
    height_cm: float | None = None
    variants: list[ShopVariantOut] = []

    class Config:
        from_attributes = True


class ShopOrderItemIn(BaseModel):
    product_id: uuid.UUID
    # Required for a product sold in pack sizes/shades.
    variant_id: uuid.UUID | None = None
    quantity: int = Field(gt=0, le=50)


class ShopOrderCreateIn(BaseModel):
    shipping_name: str = Field(min_length=1, max_length=120)
    shipping_phone: str = Field(min_length=10, max_length=15)
    shipping_address: str = Field(min_length=1, max_length=2000)
    shipping_state: str | None = Field(default=None, max_length=60)
    shipping_pincode: str | None = Field(default=None, pattern=r"^[1-9]\d{5}$")
    contact_email: str | None = Field(default=None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    payment_method: Literal["online", "cod"] = "online"
    items: list[ShopOrderItemIn] = Field(min_length=1, max_length=20)
    coupon_code: str | None = Field(default=None, max_length=40)
    # Ticked "send me offers": records marketing consent (never withdraws it).
    marketing_opt_in: bool | None = None


class ShopQuoteIn(BaseModel):
    """The cart, priced before ordering: discount, delivery, COD fee, total."""

    items: list[ShopOrderItemIn] = Field(min_length=1, max_length=20)
    coupon_code: str | None = Field(default=None, max_length=40)
    payment_method: Literal["online", "cod"] = "online"
    # With a PIN code, COD availability also reflects the courier.
    shipping_pincode: str | None = Field(default=None, pattern=r"^[1-9]\d{5}$")


class ShopQuoteOut(BaseModel):
    items_amount: float
    discount_amount: float
    shipping_fee: float
    cod_fee: float = 0
    total_amount: float
    free_shipping_above: float
    coupon_code: str | None = None
    coupon_error: str | None = None
    # Whether Cash on Delivery could be chosen for this cart, and why not.
    cod_available: bool = False
    cod_error: str | None = None


class ShopCheckoutConfigOut(BaseModel):
    shipping_fee: float
    free_shipping_above: float
    payment_window_minutes: int
    cod_enabled: bool
    cod_max_order: float
    cod_fee: float


class ShopRefundOut(BaseModel):
    id: uuid.UUID
    amount_requested: float | None
    amount_refunded: float | None
    status: str
    reason: str | None
    credit_note_number: str | None
    created_at: datetime
    processed_at: datetime | None

    class Config:
        from_attributes = True


class AdminRefundOut(ShopRefundOut):
    target_type: str
    target_id: uuid.UUID
    razorpay_payment_id: str
    razorpay_refund_id: str | None
    failure_reason: str | None
    initiated_by: uuid.UUID | None


class AdminRefundIn(BaseModel):
    """Refund on a prepaid order; leave amount empty to refund in full."""

    amount: float | None = Field(default=None, gt=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=200)


class ShopCouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=200)
    discount_type: Literal["percent", "flat"]
    discount_value: float = Field(gt=0, le=100_000)
    max_discount: float | None = Field(default=None, gt=0, le=100_000)
    min_order_amount: float = Field(default=0, ge=0, le=1_000_000)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    per_user_limit: int | None = Field(default=1, ge=1, le=1000)
    is_active: bool = True

    @field_validator("starts_at", "expires_at")
    @classmethod
    def to_naive_utc(cls, v):
        # Stored like every other timestamp here: naive UTC.
        if v is not None and v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

    @field_validator("discount_value")
    @classmethod
    def percent_in_range(cls, v, info):
        if info.data.get("discount_type") == "percent" and v > 90:
            raise ValueError("a percent discount must be 90 or less")
        return v


class ShopCouponOut(ShopCouponIn):
    id: uuid.UUID
    code: str
    uses: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ShopOrderCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class ShopOrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_id: uuid.UUID | None = None
    variant_label: str | None = None
    hsn_code: str | None = None
    gst_rate: float | None = None
    unit_price: float
    quantity: int
    subtotal: float

    class Config:
        from_attributes = True


class ShipmentEventOut(BaseModel):
    status: str
    description: str | None
    location: str | None
    occurred_at: datetime

    class Config:
        from_attributes = True


class ShopReturnOut(BaseModel):
    id: uuid.UUID
    status: str
    reason_code: str
    items: list
    refund_amount: float
    admin_note: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ShipmentOut(BaseModel):
    id: uuid.UUID
    direction: str = "forward"  # "reverse" = return pickup
    courier_name: str | None
    awb: str | None
    tracking_url: str | None
    status: str
    ndr_status: str | None = None  # "open": the customer can choose what happens next
    ndr_action: str | None = None
    ndr_raised_at: datetime | None = None
    created_at: datetime
    delivered_at: datetime | None
    events: list[ShipmentEventOut] = []

    class Config:
        from_attributes = True


class ShopOrderOut(BaseModel):
    id: uuid.UUID
    consumer_id: uuid.UUID
    shipping_name: str
    shipping_phone: str
    shipping_address: str
    shipping_state: str | None = None
    shipping_pincode: str | None = None
    contact_email: str | None = None
    invoice_number: str | None = None
    invoiced_at: datetime | None = None
    payment_method: str = "online"
    payment_status: str = "unpaid"
    amount_paid: float = 0
    amount_refunded: float = 0
    cod_fee: float = 0
    confirmed_at: datetime | None = None
    delivered_at: datetime | None = None
    total_amount: float
    status: str
    created_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    items: list[ShopOrderItemOut]
    items_amount: float | None = None
    discount_amount: float = 0
    shipping_fee: float = 0
    coupon_code: str | None = None
    courier_name: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    return_condition: str | None = None
    refunds: list[ShopRefundOut] = []
    shipments: list[ShipmentOut] = []
    returns: list[ShopReturnOut] = []
    return_window_ends: datetime | None = None  # last day a return can be asked for
    source: str | None = None  # abandoned_cart, referral, utm source, direct

    class Config:
        from_attributes = True


class ShopOrderStatusIn(BaseModel):
    status: str
    # Filled in when marking an order shipped.
    courier_name: str | None = Field(default=None, max_length=80)
    tracking_number: str | None = Field(default=None, max_length=80)
    tracking_url: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    reason: str | None = Field(default=None, max_length=200)
    condition: Literal["good", "damaged"] = "good"  # for "returned": restock only if good

    @field_validator("status")
    @classmethod
    def check_status(cls, v):
        if v not in SHOP_ORDER_STATUSES:
            raise ValueError(f"status must be one of {SHOP_ORDER_STATUSES}")
        return v


class ShopPaymentOrderOut(BaseModel):
    order_id: uuid.UUID
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float
    currency: str


class ShopPaymentVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
