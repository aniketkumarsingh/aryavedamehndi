import hashlib
import hmac
import json
from datetime import timedelta

import pytest

from app.models.notification import Notification
from app.models.shop import ShopOrder
from app.services import razorpay_client
from tests.conftest import auth_headers, make_package, make_user
from tests.test_booking_advance import _booking_payload, _confirm_booking
from tests.test_shop import _make_product, _order

SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(razorpay_client.settings, "razorpay_webhook_secret", SECRET)


def _send(client, rp_order_id, payment_id="pay_hook1", amount_paise=10000, event="payment.captured", secret=SECRET):
    body = json.dumps({
        "event": event,
        "payload": {"payment": {"entity": {"id": payment_id, "order_id": rp_order_id, "amount": amount_paise, "status": "captured"}}},
    }).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/payments/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})


def _shop_order_awaiting_payment(client, db, consumer, stock=5, qty=1):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=stock)
    order = _order(client, consumer, [{"product_id": product["id"], "quantity": qty}]).json()
    rp = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).json()
    return order, rp["razorpay_order_id"], product


def test_rejects_bad_signature(client):
    assert _send(client, "order_x", secret="wrong").status_code == 400


def test_shop_order_paid_by_webhook_when_browser_never_reports(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    res = _send(client, rp_order_id)
    assert res.status_code == 200 and res.json()["result"] == "shop_order:paid"
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["status"] == "paid"

    # Webhook retried, then the browser's late verify: both are no-ops.
    assert _send(client, rp_order_id).json()["result"] == "shop_order:already_paid"
    late = client.post(
        f"/shop/orders/{order['id']}/payment/verify",
        json={"razorpay_order_id": rp_order_id, "razorpay_payment_id": "pay_hook1", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )
    assert late.status_code == 200 and late.json()["status"] == "paid"


def test_retry_reuses_the_same_razorpay_order(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    again = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).json()
    assert again["razorpay_order_id"] == rp_order_id


def test_payment_for_expired_shop_order_is_refunded_once(client, db, consumer):
    order, rp_order_id, product = _shop_order_awaiting_payment(client, db, consumer, stock=1)
    row = db.get(ShopOrder, order["id"])
    row.created_at = row.created_at - timedelta(hours=2)
    db.commit()

    assert _send(client, rp_order_id).json()["result"] == "shop_order:refunded"
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "cancelled" and body["refund_status"] == "refunded"
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 1
    refunds_before = db.query(Notification).filter(Notification.title == "Payment refunded").count()
    _send(client, rp_order_id)
    assert db.query(Notification).filter(Notification.title == "Payment refunded").count() == refunds_before


def test_booking_advance_paid_by_webhook(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)
    booking_id = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer)).json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    rp_order_id = client.post(f"/bookings/{booking_id}/advance/order", headers=auth_headers(consumer)).json()["razorpay_order_id"]

    assert _send(client, rp_order_id, amount_paise=100000).json()["result"] == "booking_advance:paid"
    assert client.get(f"/bookings/{booking_id}", headers=auth_headers(consumer)).json()["advance_status"] == "paid"
    assert _send(client, rp_order_id).json()["result"] == "booking_advance:already_paid"


def test_unmatched_payment_alerts_admins(client, db):
    admin = make_user(db, role="admin")
    res = _send(client, "order_unknown123")
    assert res.status_code == 200 and res.json()["result"] == "unmatched"
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Unmatched payment").count() == 1


def test_other_events_are_ignored(client):
    assert _send(client, "order_x", event="payment.failed").json()["status"] == "ignored"
