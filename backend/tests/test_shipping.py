import json
from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models.notification import Notification
from app.models.shipping import Shipment, ShipmentEvent
from app.services.shipping import Booking, Serviceability, TrackingUpdate
from app.services.shipping import service as shipping_service
from tests.conftest import auth_headers, make_user, run_jobs
from tests.test_orders_payments import ADDRESS, _place
from tests.test_shop import _make_product, _pay


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


def _settings(client, admin, **values):
    assert client.put("/admin/settings", json=values, headers=auth_headers(admin)).status_code == 200


def _ship(client, admin, order_id, **details):
    return client.post(f"/admin/shipping/orders/{order_id}/shipments", json=details, headers=auth_headers(admin))


# ---------------------------------------------------------- serviceability --

def test_pincode_serviceability_and_blocks(client, admin):
    ok = client.get("/shop/serviceability", params={"pincode": "110001"}).json()
    assert ok["deliverable"] and ok["cod_available"] and ok["eta_min_days"] == 2 and len(ok["estimated_delivery"]) == 2
    assert client.get("/shop/serviceability", params={"pincode": "012345"}).status_code == 422

    _settings(client, admin, shipping_blocked_pincode_prefixes="744", shipping_cod_blocked_pincode_prefixes="79, 18")
    assert client.get("/shop/serviceability", params={"pincode": "744101"}).json()["deliverable"] is False
    no_cod = client.get("/shop/serviceability", params={"pincode": "791001"}).json()
    assert no_cod["deliverable"] and not no_cod["cod_available"]


def test_checkout_respects_pincode_rules(client, db, consumer, admin):
    _settings(client, admin, shipping_blocked_pincode_prefixes="744", shipping_cod_blocked_pincode_prefixes="791")
    product = _make_product(client, admin, price=100, stock=10)
    blocked = _place(client, consumer, product, shipping_pincode="744101")
    assert blocked.status_code == 400 and "don't deliver" in blocked.json()["detail"]
    cod = _place(client, consumer, product, shipping_pincode="791001", payment_method="cod")
    assert cod.status_code == 400 and "Cash on Delivery" in cod.json()["detail"]
    q = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "cod", "shipping_pincode": "791001"},
                    headers=auth_headers(consumer)).json()
    assert not q["cod_available"] and "PIN code" in q["cod_error"]
    assert _place(client, consumer, product, shipping_pincode="791001").status_code == 200  # online is fine


# ----------------------------------------------------------------- package --

def test_parcel_weight_and_box_from_pack_sizes(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=10)
    other = _make_product(client, admin, price=50, stock=10, name="Unweighed cone")
    client.put(f"/shop/products/{product['id']}", json={"name": product["name"], "price": 100, "weight_g": 300, "length_cm": 30, "breadth_cm": 8, "height_cm": 4},
               headers=auth_headers(admin))
    body = {**ADDRESS, "items": [{"product_id": product["id"], "quantity": 2}, {"product_id": other["id"], "quantity": 1}]}
    order = client.post("/shop/orders", json=body, headers=auth_headers(consumer)).json()
    from app.models.shop import ShopOrder

    package = shipping_service.order_package(db, db.get(ShopOrder, order["id"]))
    # 2 x 300 g + 1 x 250 g default + 100 g packaging; box: longest item vs. 20x15x10 minimum
    assert package.weight_g == 950
    assert (package.length_cm, package.breadth_cm, package.height_cm) == (30, 15, 10)


# ----------------------------------------------------------------- booking --

def test_booking_ships_the_order_once(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=5)
    order = _place(client, consumer, product).json()
    assert _ship(client, admin, order["id"], courier_name="Delhivery").status_code == 400  # unpaid
    _pay(client, consumer, order["id"])

    res = _ship(client, admin, order["id"], courier_name="Delhivery", awb="DL123", tracking_url="https://track.example/DL123")
    assert res.status_code == 200 and res.json()["status"] == "booked" and res.json()["weight_g"] == 350
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "shipped" and body["invoice_number"] and body["tracking_number"] == "DL123"
    assert body["shipments"][0]["events"][0]["status"] == "booked"
    assert _ship(client, admin, order["id"], courier_name="Delhivery").status_code == 400  # already shipped


def test_bulk_dispatch_labels_and_manifest(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=10)
    paid = _place(client, consumer, product).json()
    _pay(client, consumer, paid["id"])
    cod = _place(client, consumer, product, payment_method="cod").json()
    unpaid = _place(client, consumer, product).json()

    results = client.post("/admin/shipping/bulk-book", json={"order_ids": [paid["id"], cod["id"], unpaid["id"]], "courier_name": "Bluedart"},
                          headers=auth_headers(admin)).json()
    by_order = {r["order_id"]: r for r in results}
    assert by_order[paid["id"]]["shipment_id"] and by_order[cod["id"]]["shipment_id"]
    assert "pending order can't be shipped" in by_order[unpaid["id"]]["error"]

    ids = ",".join(r["shipment_id"] for r in results if r["shipment_id"])
    for doc in ("labels", "manifest"):
        pdf = client.get(f"/admin/shipping/{doc}.pdf", params={"ids": ids}, headers=auth_headers(admin))
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    shipments = client.get("/admin/shipping/shipments", headers=auth_headers(admin)).json()
    assert {s["cod_amount"] for s in shipments} == {0, 179}  # 100 + 49 delivery + 30 COD
    assert client.get("/admin/shipping/labels.pdf", params={"ids": ids}, headers=auth_headers(consumer)).status_code == 403


# ---------------------------------------------------------------- tracking --

def _shipped_cod_order(client, consumer, admin, product=None):
    product = product or _make_product(client, admin, price=100, stock=5)
    order = _place(client, consumer, product, payment_method="cod").json()
    shipment = _ship(client, admin, order["id"], courier_name="Delhivery", awb=f"AWB{order['id'][:6]}").json()
    return order, shipment


def _event(client, admin, shipment_id, status, **extra):
    return client.post(f"/admin/shipping/shipments/{shipment_id}/events", json={"status": status, **extra}, headers=auth_headers(admin))


def test_manual_tracking_drives_the_order(client, db, consumer, admin):
    order, shipment = _shipped_cod_order(client, consumer, admin)
    _event(client, admin, shipment["id"], "in_transit", location="Delhi hub")
    _event(client, admin, shipment["id"], "ndr", description="Customer not reachable")
    assert db.query(Notification).filter(Notification.user_id == consumer.id, Notification.title == "Delivery attempt failed").count() == 1
    _event(client, admin, shipment["id"], "out_for_delivery")  # re-attempt after the failed one
    assert db.query(Notification).filter(Notification.user_id == consumer.id, Notification.title == "Out for delivery").count() == 1
    res = _event(client, admin, shipment["id"], "delivered").json()
    assert res["status"] == "delivered"
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "delivered" and body["payment_status"] == "cod_with_courier"
    assert [e["status"] for e in body["shipments"][0]["events"]] == ["booked", "in_transit", "ndr", "out_for_delivery", "delivered"]

    # Delivered is final: a late "in transit" scan is kept in history but changes nothing.
    assert _event(client, admin, shipment["id"], "in_transit").json()["status"] == "delivered"


def test_admin_delivered_and_returned_actions_update_the_shipment(client, db, consumer, admin):
    order, shipment = _shipped_cod_order(client, consumer, admin)
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "returned", "reason": "Refused"}, headers=auth_headers(admin))
    db.expire_all()
    assert db.get(Shipment, shipment["id"]).status == "rto_delivered"


# ------------------------------------------------- courier webhooks & polls --

class FakeCourier:
    name = "fakecourier"
    live_tracking = True
    scans: list = []

    def serviceability(self, db, pincode, cod, package):
        return Serviceability(deliverable=True, cod_available=pincode != "560001", eta_min_days=1, eta_max_days=3)

    def book(self, db, order, package, details):
        return Booking(awb=f"FC{order.id.hex[:8]}", courier_name="FakeCourier", tracking_url="https://fake.example/t", label_url="https://fake.example/label.pdf")

    def track(self, awb):
        return [s for s in self.scans if s.awb == awb]

    def verify_webhook(self, headers, body):
        if headers.get("x-fake-signature") != "ok":
            raise ValueError("bad signature")
        return json.loads(body)["event_id"]

    def parse_updates(self, payload):
        return [TrackingUpdate(awb=s["awb"], status=s["status"], occurred_at=utcnow(), external_id=s["scan_id"], description=s.get("note"))
                for s in payload["scans"]]

    def cancel(self, awb):
        pass


@pytest.fixture
def fake_courier(monkeypatch):
    courier = FakeCourier()
    courier.scans = []
    monkeypatch.setattr(shipping_service, "get_provider", lambda name=None: courier)
    return courier


def test_serviceability_from_a_live_courier_is_cached(client, db, fake_courier):
    calls = []
    original = fake_courier.serviceability
    fake_courier.serviceability = lambda *a: calls.append(1) or original(*a)
    client.get("/shop/serviceability", params={"pincode": "560001"})
    second = client.get("/shop/serviceability", params={"pincode": "560001"}).json()
    assert len(calls) == 1 and second["cod_available"] is False


def test_courier_webhook_is_verified_stored_and_applied_once(client, db, consumer, admin, fake_courier):
    product = _make_product(client, admin, price=100, stock=5)
    order = _place(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    shipment = _ship(client, admin, order["id"]).json()
    assert shipment["awb"].startswith("FC") and shipment["label_url"]

    body = json.dumps({"event_id": "evt-1", "scans": [
        {"awb": shipment["awb"], "status": "picked_up", "scan_id": "s1"},
        {"awb": shipment["awb"], "status": "out_for_delivery", "scan_id": "s2"},
    ]})
    assert client.post("/shipping/webhook/fakecourier", content=body, headers={"x-fake-signature": "bad"}).status_code == 400
    assert client.post("/shipping/webhook/fakecourier", content=body, headers={"x-fake-signature": "ok"}).json()["status"] == "queued"
    assert client.post("/shipping/webhook/fakecourier", content=body, headers={"x-fake-signature": "ok"}).json()["status"] == "duplicate"
    run_jobs()
    db.expire_all()
    assert db.get(Shipment, shipment["id"]).status == "out_for_delivery"

    # The 2-hourly poll brings the same scans again plus a new one: only the new one is stored.
    fake_courier.scans = [TrackingUpdate(awb=shipment["awb"], status="out_for_delivery", occurred_at=utcnow(), external_id="s2"),
                          TrackingUpdate(awb=shipment["awb"], status="delivered", occurred_at=utcnow() + timedelta(seconds=1), external_id="s3")]
    from app.services.shipping.service import poll_tracking

    with db.begin_nested():
        assert poll_tracking(db, {}) == "1 checked, 1 new scans"
    db.commit()
    assert db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id == shipment["id"]).count() == 4  # booked + 3 scans
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["status"] == "delivered"


def test_manual_provider_has_no_webhook(client):
    assert client.post("/shipping/webhook/manual", content=b"{}").status_code == 404



# ------------------------------------------------------------- S2: money & exceptions --

def test_customer_answers_a_failed_delivery(client, db, consumer, admin):
    _settings(client, admin, shipping_cod_blocked_pincode_prefixes="791")
    order, shipment = _shipped_cod_order(client, consumer, admin)
    url = f"/shop/orders/{order['id']}/delivery-issue"
    assert client.post(url, json={"action": "reattempt"}, headers=auth_headers(consumer)).status_code == 400  # nothing failed yet

    _event(client, admin, shipment["id"], "ndr", description="Door locked")
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["shipments"][0]["ndr_status"] == "open"
    # A new address must be serviceable for COD.
    bad = client.post(url, json={"action": "change_address", "address": "Somewhere", "pincode": "791001"}, headers=auth_headers(consumer))
    assert bad.status_code == 400
    ok = client.post(url, json={"action": "change_address", "address": "22 New Street, Pune", "pincode": "411001", "phone": "9800000001"},
                     headers=auth_headers(consumer))
    assert ok.status_code == 200
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["shipping_pincode"] == "411001" and body["shipments"][0]["ndr_status"] == "answered"
    assert client.post(url, json={"action": "reattempt"}, headers=auth_headers(consumer)).status_code == 400  # already answered

    # The next scan closes the failed-delivery case.
    _event(client, admin, shipment["id"], "out_for_delivery")
    assert client.get("/admin/shipping/shipments", headers=auth_headers(admin)).json()[0]["ndr_status"] == "closed"


def test_unanswered_failed_delivery_is_reattempted_after_24h(client, db, consumer, admin):
    order, shipment = _shipped_cod_order(client, consumer, admin)
    _event(client, admin, shipment["id"], "ndr")
    row = db.get(Shipment, shipment["id"])
    row.ndr_raised_at = utcnow() - timedelta(hours=25)
    db.commit()
    from app.services.shipping.service import ndr_auto_reattempt

    with db.begin_nested():
        assert ndr_auto_reattempt(db, {}) == "1 reattempts requested"
    db.commit()
    db.expire_all()
    row = db.get(Shipment, shipment["id"])
    assert (row.ndr_status, row.ndr_action) == ("auto", "reattempt")


def test_returned_parcel_condition_decides_restock_and_prepaid_is_refunded(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=3)
    prepaid = _place(client, consumer, product).json()
    _pay(client, consumer, prepaid["id"])
    ship = _ship(client, admin, prepaid["id"], courier_name="Delhivery").json()
    _event(client, admin, ship["id"], "rto")
    res = client.post(f"/admin/shipping/shipments/{ship['id']}/receive-return", json={"condition": "damaged", "note": "Box crushed"},
                      headers=auth_headers(admin))
    assert res.status_code == 200 and res.json()["status"] == "rto_delivered"
    run_jobs()
    body = client.get(f"/shop/orders/{prepaid['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "returned" and body["return_condition"] == "damaged" and body["payment_status"] == "refunded"
    assert body["refunds"][0]["credit_note_number"] is None or body["refunds"][0]["credit_note_number"].startswith("CN")
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 2  # damaged: not restocked

    order, cod_ship = _shipped_cod_order(client, consumer, admin, product)
    client.post(f"/admin/shipping/shipments/{cod_ship['id']}/receive-return", json={"condition": "good"}, headers=auth_headers(admin))
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["payment_status"] == "void"
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 2  # good: back in stock
    assert client.post(f"/admin/shipping/shipments/{cod_ship['id']}/receive-return", json={"condition": "good"}, headers=auth_headers(admin)).status_code == 400


def test_unremitted_cod_is_flagged_by_reconciliation(client, db, consumer, admin):
    order, shipment = _shipped_cod_order(client, consumer, admin)
    _event(client, admin, shipment["id"], "delivered")
    row = db.get(Shipment, shipment["id"])
    row.delivered_at = utcnow() - timedelta(days=11)
    db.commit()
    assert [s["id"] for s in client.get("/admin/shipping/cod-unremitted", params={"older_than_days": 10}, headers=auth_headers(admin)).json()] == [shipment["id"]]
    from app.services.reconciliation import reconcile

    run = reconcile(db)
    assert run.status == "issues" and run.issues[0]["type"] == "cod_not_remitted"
    db.commit()
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "COD not remitted").count() == 1

    # Remittance before delivery is refused; after, it clears the flag.
    order2, undelivered = _shipped_cod_order(client, consumer, admin)
    assert client.post("/admin/shipping/cod-remittances", json={"shipment_ids": [undelivered["id"]], "reference": "UTR9"}, headers=auth_headers(admin)).status_code == 400
    client.post("/admin/shipping/cod-remittances", json={"shipment_ids": [shipment["id"]], "reference": "UTR9"}, headers=auth_headers(admin))
    assert client.get("/admin/shipping/cod-unremitted", headers=auth_headers(admin)).json() == []


def test_shipping_cost_report(client, db, consumer, admin):
    order, shipment = _shipped_cod_order(client, consumer, admin)
    client.put(f"/admin/shipping/shipments/{shipment['id']}", json={"shipping_charge": 62.5}, headers=auth_headers(admin))
    report = client.get("/admin/shipping/report", headers=auth_headers(admin)).json()
    assert report[0]["parcels"] == 1 and report[0]["fees_collected"] == 79 and report[0]["courier_charges"] == 62.5
    assert report[0]["margin"] == 16.5 and report[0]["parcels_without_charge"] == 0
