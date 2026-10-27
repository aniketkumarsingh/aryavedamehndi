"""Courier-neutral shipping.

Business code talks to `get_provider()` and the dataclasses below, never
to a courier's API directly. Each provider maps its own statuses onto ours
(app/models/shipping.py: SHIPMENT_STATUSES). To add a courier (Shiprocket,
Delhivery...), write a class with the ShippingProvider methods, register
it in PROVIDERS, and set SHIPPING_PROVIDER - nothing else changes.

"manual" is the default: no courier account; the admin enters the courier
name and AWB, and tracking is updated by hand. It still checks PIN codes
(against admin-set blocked prefixes), weighs and sizes the parcel, prints
labels and a manifest, and drives the same order/notification flow.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.config import get_settings


@dataclass(frozen=True)
class Package:
    weight_g: int
    length_cm: float
    breadth_cm: float
    height_cm: float


@dataclass(frozen=True)
class Serviceability:
    deliverable: bool
    cod_available: bool
    eta_min_days: int | None = None
    eta_max_days: int | None = None


@dataclass
class Booking:
    awb: str | None
    courier_name: str | None
    tracking_url: str | None = None
    label_url: str | None = None
    pickup_scheduled_at: datetime | None = None
    shipping_charge: float | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingUpdate:
    awb: str
    status: str  # one of SHIPMENT_STATUSES
    occurred_at: datetime
    external_id: str  # unique per scan, for de-duplication
    description: str | None = None
    location: str | None = None
    raw: dict | None = None


class ShippingError(Exception):
    """The provider refused (shown to the admin as-is)."""


class WebhookNotSupported(Exception):
    pass


class ShippingProvider(Protocol):
    name: str
    live_tracking: bool  # True if track() can fetch scans from the courier

    def serviceability(self, db, pincode: str, cod: bool, package: Package | None) -> Serviceability: ...

    def book(self, db, order, package: Package, details: dict) -> Booking: ...

    def track(self, awb: str) -> list[TrackingUpdate]: ...

    def verify_webhook(self, headers: dict, body: bytes) -> str:
        """Checks the courier's signature; returns a key identifying this
        event (for de-duplication). Raises ValueError if it doesn't verify."""
        ...

    def parse_updates(self, payload: dict) -> list[TrackingUpdate]:
        """Tracking scans in a (stored, already verified) webhook payload."""
        ...

    def cancel(self, awb: str) -> None: ...


def get_provider(name: str | None = None) -> ShippingProvider:
    from app.services.shipping.manual import ManualProvider

    providers = {"manual": ManualProvider}
    key = name or get_settings().shipping_provider
    if key not in providers:
        raise ShippingError(f"Unknown shipping provider {key!r}")
    return providers[key]()
