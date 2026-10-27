import io
import json
from datetime import timedelta

import pytest
from PIL import Image

from app.core.time import utcnow
from app.models.booking import Booking
from app.models.notification import Notification
from app.models.shop import ShopOrder, ShopProduct
from tests.conftest import auth_headers, make_package, make_user, run_jobs
from tests.test_booking_advance import _booking_payload, _confirm_booking
from tests.test_orders_payments import _place
from tests.test_shop import _make_product, _pay


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 80, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _delivered(client, db, consumer, admin, price=100, qty=2, cod=False, returnable=True):
    product = _make_product(client, admin, price=price, stock=10)
    if not returnable:
        row = db.get(ShopProduct, product["id"])
        row.returnable = False
        db.commit()
    order = _place(client, consumer, product, qty=qty, **({"payment_method": "cod"} if cod else {})).json()
    if not cod:
        _pay(client, consumer, order["id"])
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped", "courier_name": "Delhivery"}, headers=auth_headers(admin))
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "delivered"}, headers=auth_headers(admin))
    order = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    return product, order


def _ask(client, consumer, order, qty=1, reason="changed_mind", photos=0, **extra):
    data = {"items": json.dumps([{"order_item_id": order["items"][0]["id"], "quantity": qty}]), "reason_code": reason, **extra}
    files = [("photos", (f"p{i}.png", _png(), "image/png")) for i in range(photos)]
    return client.post(f"/shop/orders/{order['id']}/returns", data=data, files=files or None, headers=auth_headers(consumer))


def test_return_rules(client, db, consumer, admin):
    product, order = _delivered(client, db, consumer, admin, qty=2)
    assert order["return_window_ends"]
    assert _ask(client, consumer, order, qty=3).status_code == 400  # more than bought
    assert _ask(client, consumer, order, reason="damaged").status_code == 400  # damaged needs a photo
    first = _ask(client, consumer, order, qty=1)
    assert first.status_code == 200 and first.json()["refund_amount"] == 100
    assert _ask(client, consumer, order, qty=2).status_code == 400  # only 1 left to return

    row = db.get(ShopOrder, order["id"])
    row.delivered_at = utcnow() - timedelta(days=8)
    db.commit()
    late = _ask(client, consumer, order, qty=1)
    assert late.status_code == 400 and "window" in late.json()["detail"]


def test_non_returnable_products_only_for_damage_with_photo(client, db, consumer, admin):
    _, order = _delivered(client, db, consumer, admin, qty=1, returnable=False)
    refused = _ask(client, consumer, order, reason="changed_mind")
    assert refused.status_code == 400 and "hygiene" in refused.json()["detail"]
    ok = _ask(client, consumer, order, reason="damaged", photos=1, details="Jar cracked")
    assert ok.status_code == 200 and ok.json()["photo_urls"]
    # Whole order damaged: delivery charge comes back too (100 + 49).
    assert ok.json()["refund_amount"] == 149


def test_prepaid_return_end_to_end(client, db, consumer, admin):
    product, order = _delivered(client, db, consumer, admin, qty=2)
    req = _ask(client, consumer, order, qty=1).json()
    approved = client.post(f"/admin/returns/{req['id']}/approve", json={"courier_name": "Delhivery", "awb": "REV1"}, headers=auth_headers(admin))
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    reverse = [s for s in body["shipments"] if s["direction"] == "reverse"]
    assert reverse and reverse[0]["awb"] == "REV1"
    # The return pickup's tracking doesn't touch the order.
    client.post(f"/admin/shipping/shipments/{reverse[0]['id']}/events", json={"status": "picked_up"}, headers=auth_headers(admin))
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["status"] == "delivered"
    labels = client.get("/admin/shipping/labels.pdf", params={"ids": reverse[0]["id"]}, headers=auth_headers(admin))
    assert labels.content.startswith(b"%PDF")

    received = client.post(f"/admin/returns/{req['id']}/receive", json={"condition": "good"}, headers=auth_headers(admin))
    assert received.status_code == 200 and received.json()["status"] == "received"
    run_jobs()
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["returns"][0]["status"] == "refunded"
    assert body["payment_status"] == "partially_refunded" and body["amount_refunded"] == 100
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 9  # 10 - 2 + 1 back


def test_cod_return_is_refunded_by_upi_with_reference(client, db, consumer, admin):
    _, order = _delivered(client, db, consumer, admin, qty=1, cod=True)
    assert _ask(client, consumer, order, reason="changed_mind").status_code == 400  # needs a UPI ID
    req = _ask(client, consumer, order, reason="changed_mind", refund_upi="priya@okicici").json()
    client.post(f"/admin/returns/{req['id']}/approve", json={}, headers=auth_headers(admin))
    no_ref = client.post(f"/admin/returns/{req['id']}/receive", json={"condition": "damaged"}, headers=auth_headers(admin))
    assert no_ref.status_code == 400 and "priya@okicici" in no_ref.json()["detail"]
    done = client.post(f"/admin/returns/{req['id']}/receive", json={"condition": "damaged", "upi_reference": "UTR998877"}, headers=auth_headers(admin))
    assert done.json()["status"] == "refunded"
    refunds = client.get("/admin/payments/refunds", headers=auth_headers(admin)).json()
    assert refunds[0]["status"] == "processed" and refunds[0]["amount_refunded"] == 100


def test_rejecting_a_return(client, db, consumer, admin):
    _, order = _delivered(client, db, consumer, admin, qty=1)
    req = _ask(client, consumer, order).json()
    assert client.post(f"/admin/returns/{req['id']}/reject", json={"note": "Item used"}, headers=auth_headers(admin)).json()["status"] == "rejected"
    assert db.query(Notification).filter(Notification.user_id == consumer.id, Notification.title == "Return not approved").count() == 1
    assert _ask(client, consumer, order).status_code == 200  # a rejected request frees the items


# ------------------------------------------------------------- bulk orders --

def test_bulk_order_goods_shipment(client, db, consumer, admin):
    from app.models.bulk_order import BulkOrder

    bulk = BulkOrder(consumer_id=consumer.id, status="confirmed", occasion="wedding", event_at=utcnow() + timedelta(days=5), address_text="Venue, Jaipur")
    db.add(bulk)
    db.commit()
    res = client.post(f"/admin/shipping/bulk-orders/{bulk.id}/shipments", json={"courier_name": "Bluedart", "awb": "BD1", "description": "50 mehndi cones"},
                      headers=auth_headers(admin))
    assert res.status_code == 200 and res.json()["reference"].startswith("BULK")
    client.post(f"/admin/shipping/shipments/{res.json()['id']}/events", json={"status": "delivered"}, headers=auth_headers(admin))
    body = client.get(f"/bulk-orders/{bulk.id}", headers=auth_headers(consumer)).json()
    assert body["shipments"][0]["status"] == "delivered"
    assert client.get("/admin/shipping/labels.pdf", params={"ids": res.json()["id"]}, headers=auth_headers(admin)).content.startswith(b"%PDF")


# --------------------------------------------------------------- SLA --

def test_artist_reminded_then_admins_alerted_when_late(client, db, consumer, artist_with_profile, admin):
    from app.services.booking_sla import sla_check

    artist_user, artist_profile = artist_with_profile
    package = make_package(db)
    booking_id = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer)).json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    row = db.get(Booking, booking_id)
    row.scheduled_at = utcnow() + timedelta(minutes=30)
    db.commit()
    with db.begin_nested():
        assert sla_check(db, {}) == "1 reminded, 0 late alerts"
    db.commit()
    row.scheduled_at = utcnow() - timedelta(minutes=20)
    db.commit()
    with db.begin_nested():
        assert sla_check(db, {}) == "0 reminded, 1 late alerts"
        assert sla_check(db, {}) == "0 reminded, 0 late alerts"  # once only
    db.commit()
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Artist not on the way").count() == 1
