import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.shop import SHOP_ORDER_STATUSES


class ShopProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    price: float = Field(gt=0, le=100_000)
    stock_quantity: int = Field(ge=0, le=100_000, default=0)


class ShopProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: float
    stock_quantity: int
    image_urls: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ShopOrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, le=50)


class ShopOrderCreateIn(BaseModel):
    shipping_name: str = Field(min_length=1, max_length=120)
    shipping_phone: str = Field(min_length=10, max_length=15)
    shipping_address: str = Field(min_length=1, max_length=2000)
    items: list[ShopOrderItemIn] = Field(min_length=1, max_length=20)


class ShopOrderItemOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    unit_price: float
    quantity: int
    subtotal: float

    class Config:
        from_attributes = True


class ShopOrderOut(BaseModel):
    id: uuid.UUID
    consumer_id: uuid.UUID
    shipping_name: str
    shipping_phone: str
    shipping_address: str
    total_amount: float
    status: str
    created_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    items: list[ShopOrderItemOut]

    class Config:
        from_attributes = True


class ShopOrderStatusIn(BaseModel):
    status: str

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
