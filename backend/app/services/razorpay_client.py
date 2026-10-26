"""Thin Razorpay REST client over plain HTTP, so the backend doesn't
depend on the `razorpay` PyPI package (which pulls in the deprecated
`pkg_resources` and breaks on newer setuptools). Covers:

- Orders + payment-signature verification (platform-fee-only flow, and the
  full-escrow flow once an artist has a Route linked account).
- Razorpay Route: linked accounts (payout destination for artists) and
  order-level transfers (the actual consumer->platform->artist split).

Everything here has a dev-stub fallback when RAZORPAY_KEY_ID/SECRET (or,
for Route, an artist's linked account) aren't set, so the booking and
payment flow can be exercised end-to-end locally without a real account.
"""

import hashlib
import hmac

import httpx

from app.config import get_settings

settings = get_settings()

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
RAZORPAY_API_BASE_V2 = "https://api.razorpay.com/v2"


def _configured() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def _client() -> httpx.Client:
    return httpx.Client(timeout=10, auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_order(amount_rupees: float, receipt: str, transfers: list[dict] | None = None) -> dict:
    """Creates a Razorpay order for `amount_rupees`. If `transfers` is
    given (Route split - see build_transfer), Razorpay auto-splits the
    payment across linked accounts as soon as it's captured."""
    amount_paise = int(round(amount_rupees * 100))

    if not _configured():
        return {
            "id": f"order_dev_{receipt}",
            "amount": amount_paise,
            "currency": "INR",
            "status": "created",
            "transfers": transfers or [],
        }

    body = {"amount": amount_paise, "currency": "INR", "receipt": receipt, "payment_capture": 1}
    if transfers:
        body["transfers"] = transfers

    with _client() as client:
        resp = client.post(f"{RAZORPAY_API_BASE}/orders", json=body)
        resp.raise_for_status()
        return resp.json()


def build_transfer(linked_account_id: str, amount_rupees: float) -> dict:
    return {"account": linked_account_id, "amount": int(round(amount_rupees * 100)), "currency": "INR", "on_hold": False}


def is_configured() -> bool:
    return _configured()


def refund_payment(payment_id: str, amount_rupees: float | None = None, receipt: str | None = None) -> dict:
    """Refunds a captured payment - in full by default. A full refund returns
    exactly what was captured, which can be less than our order total when a
    Razorpay Offer (bank/UPI/wallet discount) applied at checkout; asking for
    the order total would then be rejected. Dev-stub: if the payment was
    never a real Razorpay payment (dev-mode "dev_payment" id), there's
    nothing to actually refund - just report success."""
    if not _configured() or payment_id == "dev_payment" or payment_id.startswith("pay_dev"):
        return {"id": f"rfnd_dev_{receipt or payment_id}", "status": "processed", "amount": None}

    # `receipt` (our refund id) lets a retry find a refund that Razorpay
    # created even though our side never saw the response - see find_refund.
    body = {} if amount_rupees is None else {"amount": int(round(amount_rupees * 100))}
    if receipt:
        body["receipt"] = receipt
        body["notes"] = {"refund_id": receipt}
    with _client() as client:
        resp = client.post(f"{RAZORPAY_API_BASE}/payments/{payment_id}/refund", json=body)
        resp.raise_for_status()
        return resp.json()


def find_refund(payment_id: str, receipt: str) -> dict | None:
    """A refund on this payment carrying our receipt, if Razorpay has one."""
    if not _configured() or payment_id == "dev_payment" or payment_id.startswith("pay_dev"):
        return None
    with _client() as client:
        resp = client.get(f"{RAZORPAY_API_BASE}/payments/{payment_id}/refunds", params={"count": 100})
        resp.raise_for_status()
    for refund in resp.json().get("items", []):
        if refund.get("receipt") == receipt or (refund.get("notes") or {}).get("refund_id") == receipt:
            return refund
    return None


def fetch_refund(payment_id: str, refund_id: str) -> dict:
    with _client() as client:
        resp = client.get(f"{RAZORPAY_API_BASE}/payments/{payment_id}/refunds/{refund_id}")
        resp.raise_for_status()
        return resp.json()


def fetch_payment(payment_id: str) -> dict:
    with _client() as client:
        resp = client.get(f"{RAZORPAY_API_BASE}/payments/{payment_id}")
        resp.raise_for_status()
        return resp.json()


def list_payments(from_ts: int, to_ts: int) -> list[dict]:
    """Every payment created in [from_ts, to_ts] (unix seconds), all pages."""
    items, skip = [], 0
    with _client() as client:
        while True:
            resp = client.get(f"{RAZORPAY_API_BASE}/payments", params={"from": from_ts, "to": to_ts, "count": 100, "skip": skip})
            resp.raise_for_status()
            page = resp.json().get("items", [])
            items.extend(page)
            if len(page) < 100:
                return items
            skip += 100


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    """Razorpay signs each webhook body with the webhook secret set in the
    dashboard (Settings -> Webhooks), separately from the API key secret."""
    if not settings.razorpay_webhook_secret or not signature:
        return False
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not _configured():
        return order_id.startswith("order_dev_")  # dev-mode auto-pass

    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(settings.razorpay_key_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_linked_account(artist_name: str, phone: str, pan_number: str | None, bank: dict) -> str:
    """Creates a Razorpay Route linked account for an artist, so future
    bookings can be paid in full by the consumer with the artist's share
    auto-transferred. Requires real business onboarding info once a real
    Razorpay Route account is in place (this is a simplified skeleton -
    check Razorpay's current /v2/accounts docs before going live: real
    accounts typically also need an email, address and business category).

    Returns the linked account id (fake in dev mode).
    """
    if not _configured():
        import uuid

        return f"acc_dev_{uuid.uuid4().hex[:14]}"

    body = {
        "email": f"{phone}@aryavedamehndi-artists.example",
        "phone": phone,
        "type": "route",
        "reference_id": phone,
        "legal_business_name": artist_name,
        "business_type": "individual",
        "contact_name": artist_name,
        "profile": {"category": "healthcare", "subcategory": "wellness"},
        "legal_info": {"pan": pan_number} if pan_number else {},
    }
    with _client() as client:
        resp = client.post(f"{RAZORPAY_API_BASE_V2}/accounts", json=body)
        resp.raise_for_status()
        account_id = resp.json()["id"]

        # Attach the bank account as the payout destination for this
        # linked account (Route "stakeholder"/"product configuration"
        # flow - the exact sub-resource depends on Razorpay's current API
        # version, verify against their docs before relying on this).
        client.post(
            f"{RAZORPAY_API_BASE_V2}/accounts/{account_id}/products",
            json={
                "product_name": "route",
                "tnc_accepted": True,
                "settlements": {
                    "account_number": bank.get("account_number"),
                    "ifsc_code": bank.get("ifsc_code"),
                    "beneficiary_name": bank.get("account_holder_name"),
                },
            },
        )
    return account_id
