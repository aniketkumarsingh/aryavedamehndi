import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest

from app.models.notification import Notification
from app.models.payment_ops import PaymentEvent, Refund
from app.models.shop import ShopOrder
from app.services import razorpay_client
from tests.conftest import auth_headers, make_package, make_user, run_jobs
from tests.test_booking_advance import _booking_payload, _confirm_booking
from tests.test_shop import _make_product, _order

SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(razorpay_client.settings, "razorpay_webhook_secret", SECRET)


def _send(client, rp_order_id, payment_id="pay_hook1", amount_paise=14900, event="payment.captured", secret=SECRET, event_id=None, entity=None):
    body = json.dumps({
        "event": event,
        "payload": entity or {"payment": {"entity": {"id": payment_id, "order_id": rp_order_id, "amount": amount_paise, "status": "captured"}}},
    }).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json", "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:12]}"}
    return client.post("/payments/razorpay/webhook", content=body, headers=headers)


def _result(db, event_id):
    db.expire_all()
    return db.query(PaymentEvent).filter(PaymentEvent.event_id == event_id).one()


def _shop_order_awaiting_payment(client, db, consumer, stock=5, qty=1):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=stock)
    order = _order(client, consumer, [{"product_id": product["id"], "quantity": qty}]).json()
    rp = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).json()
    return order, rp["razorpay_order_id"], product


def test_rejects_bad_signature(client):
    assert _send(client, "order_x", secret="wrong").status_code == 400


def test_event_is_stored_and_answered_before_processing(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    res = _send(client, rp_order_id, event_id="evt_store1")
    assert res.status_code == 200 and res.json()["status"] == "queued"
    assert _result(db, "evt_store1").status == "received"
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["status"] == "pending"

    run_jobs()
    event = _result(db, "evt_store1")
    assert event.status == "processed" and event.result == "shop_order:paid"
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "confirmed" and body["payment_status"] == "paid" and body["amount_paid"] == 149


def test_redelivered_event_is_processed_once(client, db, consumer):
    _, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    assert _send(client, rp_order_id, event_id="evt_dup").json()["status"] == "queued"
    assert _send(client, rp_order_id, event_id="evt_dup").json()["status"] == "duplicate"
    run_jobs()
    assert db.query(PaymentEvent).filter(PaymentEvent.event_id == "evt_dup").count() == 1


def test_webhook_and_browser_verify_settle_once(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    _send(client, rp_order_id, payment_id="pay_both", event_id="evt_both")
    run_jobs()
    late = client.post(
        f"/shop/orders/{order['id']}/payment/verify",
        json={"razorpay_order_id": rp_order_id, "razorpay_payment_id": "pay_both", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )
    assert late.status_code == 200 and late.json()["payment_status"] == "paid"
    assert db.query(Notification).filter(Notification.user_id == consumer.id, Notification.title == "Order confirmed").count() == 1


def test_offer_discounted_capture_records_the_captured_amount(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    _send(client, rp_order_id, amount_paise=12900)  # Razorpay Offer took ₹20 off at checkout
    run_jobs()
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["amount_paid"] == 129


def test_retry_reuses_the_same_razorpay_order(client, db, consumer):
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    again = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).json()
    assert again["razorpay_order_id"] == rp_order_id


def test_payment_for_expired_shop_order_is_refunded_once(client, db, consumer):
    order, rp_order_id, product = _shop_order_awaiting_payment(client, db, consumer, stock=1)
    row = db.get(ShopOrder, order["id"])
    row.created_at = row.created_at - timedelta(hours=2)
    db.commit()

    _send(client, rp_order_id, event_id="evt_late1")
    run_jobs()
    assert _result(db, "evt_late1").result == "shop_order:refunded"
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "cancelled" and body["payment_status"] == "refunded"
    assert [r["status"] for r in body["refunds"]] == ["processed"]
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 1

    _send(client, rp_order_id, event_id="evt_late2")  # same payment, delivered again
    run_jobs()
    assert db.query(Refund).filter(Refund.target_id == uuid.UUID(order["id"])).count() == 1


def test_booking_advance_paid_by_webhook(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)
    booking_id = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer)).json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    rp_order_id = client.post(f"/bookings/{booking_id}/advance/order", headers=auth_headers(consumer)).json()["razorpay_order_id"]

    _send(client, rp_order_id, amount_paise=100000, event_id="evt_adv")
    run_jobs()
    assert _result(db, "evt_adv").result == "booking_advance:paid"
    assert client.get(f"/bookings/{booking_id}", headers=auth_headers(consumer)).json()["advance_status"] == "paid"


def test_unmatched_payment_alerts_admins(client, db):
    admin = make_user(db, role="admin")
    _send(client, "order_unknown123", event_id="evt_unknown")
    run_jobs()
    assert _result(db, "evt_unknown").result == "unmatched"
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Unmatched payment").count() == 1


def test_other_events_are_stored_but_ignored(client, db):
    assert _send(client, "order_x", event="payment.failed", event_id="evt_failed").json()["status"] == "ignored"
    run_jobs()
    assert _result(db, "evt_failed").status == "ignored"


def test_refund_webhooks_complete_and_fail_refunds(client, db, consumer, monkeypatch):
    from app.services import refunds as refunds_service

    admin = make_user(db, role="admin")
    order, rp_order_id, _ = _shop_order_awaiting_payment(client, db, consumer)
    _send(client, rp_order_id, payment_id="pay_r1")
    run_jobs()

    # Razorpay accepts refunds as "pending" and confirms later by webhook.
    monkeypatch.setattr(refunds_service.razorpay_client, "refund_payment", lambda pid, amt=None, receipt=None: {"id": f"rfnd_{receipt[:6]}", "status": "pending", "amount": None})
    client.post(f"/shop/orders/{order['id']}/cancel", json={}, headers=auth_headers(consumer))
    run_jobs()
    refund = db.query(Refund).one()
    assert refund.status == "submitted"
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["payment_status"] == "refund_pending"

    entity = {"refund": {"entity": {"id": refund.razorpay_refund_id, "payment_id": "pay_r1", "amount": 14900, "status": "processed"}}}
    _send(client, None, event="refund.processed", entity=entity)
    run_jobs()
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["payment_status"] == "refunded" and body["amount_refunded"] == 149
    assert body["refunds"][0]["status"] == "processed"

    # A failure webhook on another refund alerts admins.
    other = Refund(target_type="shop_order", target_id=uuid.UUID(order["id"]), razorpay_payment_id="pay_r1", razorpay_refund_id="rfnd_fail", amount_requested=10, status="submitted")
    db.add(other)
    db.commit()
    _send(client, None, event="refund.failed", entity={"refund": {"entity": {"id": "rfnd_fail", "status": "failed"}}})
    run_jobs()
    db.expire_all()
    assert db.get(Refund, other.id).status == "failed"
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Refund failed").count() == 1
