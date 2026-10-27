"""The manual provider: no courier account. Serviceability comes from the
admin's settings; booking records what the admin typed (courier, AWB,
tracking link); tracking is updated by hand from the admin panel."""

from app.services.platform_settings import get_platform_settings
from app.services.shipping import Booking, Package, Serviceability, TrackingUpdate, WebhookNotSupported


def _prefixes(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


class ManualProvider:
    name = "manual"
    live_tracking = False

    def serviceability(self, db, pincode: str, cod: bool, package: Package | None) -> Serviceability:
        s = get_platform_settings(db)
        if any(pincode.startswith(p) for p in _prefixes(s["shipping_blocked_pincode_prefixes"])):
            return Serviceability(deliverable=False, cod_available=False)
        cod_ok = not any(pincode.startswith(p) for p in _prefixes(s["shipping_cod_blocked_pincode_prefixes"]))
        return Serviceability(deliverable=True, cod_available=cod_ok,
                              eta_min_days=int(s["shipping_eta_min_days"]), eta_max_days=int(s["shipping_eta_max_days"]))

    def book(self, db, order, package: Package, details: dict) -> Booking:
        courier = (details.get("courier_name") or "").strip() or None  # blank for hand delivery
        tracking_url = (details.get("tracking_url") or "").strip() or None
        if tracking_url and not tracking_url.startswith(("http://", "https://")):
            raise ShippingError("The tracking link must start with http:// or https://")
        return Booking(awb=(details.get("awb") or "").strip() or None, courier_name=courier, tracking_url=tracking_url)

    def track(self, awb: str) -> list[TrackingUpdate]:
        return []

    def verify_webhook(self, headers: dict, body: bytes) -> str:
        raise WebhookNotSupported("The manual provider has no webhooks")

    def parse_updates(self, payload: dict) -> list[TrackingUpdate]:
        return []

    def cancel(self, awb: str) -> None:
        return None

    def ndr_action(self, awb: str, action: str, details: dict) -> None:
        return None  # an admin passes it on to the courier (they're notified)

    def cod_remittances(self, since):
        return []  # recorded by hand from the courier's remittance statement
