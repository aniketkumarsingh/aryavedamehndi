from datetime import timedelta
from io import BytesIO

from PIL import Image

from app.core.time import utcnow
from app.models.bulk_order import BulkOrder
from app.models.catalog import Design
from app.services.platform_settings import update_platform_settings
from tests.conftest import auth_headers, make_package, make_user, run_jobs


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), (120, 60, 20)).save(buf, format="PNG")
    return buf.getvalue()


def _design(db, package, price_min=4000, price_max=6000):
    design = Design(package_id=package.id, name="Royal Jaal", price_min=price_min, price_max=price_max, duration_minutes=180)
    db.add(design)
    db.commit()
    db.refresh(design)
    return design


def _event_at(days=10):
    return (utcnow() + timedelta(days=days)).isoformat()


def _order_payload(lines, **overrides):
    payload = {
        "occasion": "mehndi-ceremony",
        "event_at": _event_at(),
        "address_text": "Sharma Niwas, 4 Civil Lines, Jaipur",
        "lines": lines,
    }
    payload.update(overrides)
    return payload


def _quote(client, admin, order, prices):
    lines = [{"line_id": l["id"], "unit_price": p} for l, p in zip(order["lines"], prices)]
    return client.post(f"/admin/bulk-orders/{order['id']}/quote", json={"lines": lines}, headers=auth_headers(admin))


def _pay_deposit(client, consumer, order_id):
    rp = client.post(f"/bulk-orders/{order_id}/advance/order", headers=auth_headers(consumer)).json()
    return client.post(
        f"/bulk-orders/{order_id}/advance/verify",
        json={"razorpay_order_id": rp["razorpay_order_id"], "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )


def test_estimate_is_the_sum_of_per_person_bookings(client, db):
    guests = make_package(db, price_min=500, price_max=1500, advance_amount=200)
    bridal = make_package(db, package_type="bridal", price_min=3000, price_max=9000, advance_amount=1000)
    design = _design(db, bridal)  # its own 4000-6000 band replaces the package's

    res = client.post(
        "/pricing/estimate",
        json={"lines": [{"package_id": str(guests.id), "quantity": 20}, {"package_id": str(bridal.id), "design_id": str(design.id), "quantity": 1}]},
    )
    assert res.status_code == 200
    est = res.json()
    assert est["people"] == 21
    assert est["subtotal_min"] == 20 * 500 + 4000
    assert est["subtotal_max"] == 20 * 1500 + 6000
    # default 10% fee, per person - same as each booking's compute_platform_fee
    assert est["platform_fee_min"] == 20 * 50 + 400
    assert est["total_max"] == est["subtotal_max"] + est["platform_fee_max"]
    assert est["advance_amount"] == 20 * 200 + 1000


def test_flat_fee_is_charged_per_person_not_per_order(client, db):
    update_platform_settings(db, {"platform_fee_mode": "flat", "platform_fee_flat": 49})
    db.commit()
    package = make_package(db, price_min=500, price_max=1500)
    est = client.post("/pricing/estimate", json={"lines": [{"package_id": str(package.id), "quantity": 10}]}).json()
    assert est["platform_fee_min"] == est["platform_fee_max"] == 490


def test_pricing_policy_is_public(client):
    res = client.get("/pricing/policy")
    assert res.status_code == 200
    assert set(res.json()) == {"platform_fee_mode", "platform_fee_percent", "platform_fee_flat"}


def test_bulk_order_quote_must_stay_inside_each_band(client, db, consumer):
    admin = make_user(db, role="admin")
    package = make_package(db, price_min=500, price_max=1500, advance_amount=200)
    create = client.post(
        "/bulk-orders", json=_order_payload([{"package_id": str(package.id), "quantity": 15}]), headers=auth_headers(consumer)
    )
    assert create.status_code == 200, create.text
    order = create.json()
    assert order["status"] == "requested"
    assert order["advance_amount"] == 15 * 200
    assert order["advance_status"] == "pending"

    # a "bulk discount" below the band is refused, like any booking would be
    assert _quote(client, admin, order, [400]).status_code == 400
    assert _quote(client, admin, order, [1600]).status_code == 400

    quoted = _quote(client, admin, order, [1000])
    assert quoted.status_code == 200
    body = quoted.json()
    assert body["status"] == "quoted"
    assert body["subtotal"] == 15000
    assert body["platform_fee"] == 1500
    assert body["total_amount"] == 16500


def test_full_bulk_order_flow_with_deposit(client, db, consumer):
    admin = make_user(db, role="admin")
    package = make_package(db, advance_amount=300)
    order = client.post(
        "/bulk-orders", json=_order_payload([{"package_id": str(package.id), "quantity": 4}]), headers=auth_headers(consumer)
    ).json()
    _quote(client, admin, order, [2000])

    accepted = client.post(f"/bulk-orders/{order['id']}/accept", headers=auth_headers(consumer))
    assert accepted.json()["status"] == "confirmed"

    # can't complete before the deposit is in
    assert client.post(f"/admin/bulk-orders/{order['id']}/complete", headers=auth_headers(admin)).status_code == 400
    paid = _pay_deposit(client, consumer, order["id"])
    assert paid.json()["advance_status"] == "paid"

    done = client.post(f"/admin/bulk-orders/{order['id']}/complete", headers=auth_headers(admin))
    assert done.json()["status"] == "completed"


def test_deposit_refunded_early_forfeited_late(client, db, consumer):
    admin = make_user(db, role="admin")
    package = make_package(db, advance_amount=300)

    def confirmed_paid_order():
        order = client.post(
            "/bulk-orders", json=_order_payload([{"package_id": str(package.id), "quantity": 2}]), headers=auth_headers(consumer)
        ).json()
        _quote(client, admin, order, [2000])
        client.post(f"/bulk-orders/{order['id']}/accept", headers=auth_headers(consumer))
        _pay_deposit(client, consumer, order["id"])
        return order["id"]

    early = confirmed_paid_order()
    res = client.post(f"/bulk-orders/{early}/cancel", json={}, headers=auth_headers(consumer))
    assert res.json()["status"] == "cancelled"
    assert res.json()["advance_status"] == "refund_pending"
    run_jobs()
    assert client.get(f"/bulk-orders/{early}", headers=auth_headers(consumer)).json()["advance_status"] == "refunded"

    late = confirmed_paid_order()
    row = db.get(BulkOrder, late)
    row.event_at = utcnow() + timedelta(hours=5)
    db.commit()
    res = client.post(f"/bulk-orders/{late}/cancel", json={}, headers=auth_headers(consumer))
    assert res.json()["advance_status"] == "forfeited"


def test_bulk_order_validation(client, db, consumer, package):
    line = [{"package_id": str(package.id), "quantity": 3}]
    too_soon = _order_payload(line, event_at=(utcnow() + timedelta(hours=2)).isoformat())
    assert client.post("/bulk-orders", json=too_soon, headers=auth_headers(consumer)).status_code == 400
    assert client.post("/bulk-orders", json=_order_payload(line, occasion="rave"), headers=auth_headers(consumer)).status_code == 422
    external = [{"package_id": str(package.id), "quantity": 3, "reference_image_url": "http://evil.example/x.png"}]
    assert client.post("/bulk-orders", json=_order_payload(external), headers=auth_headers(consumer)).status_code == 422


def test_bulk_orders_are_private(client, db, consumer, package):
    other = make_user(db, role="consumer")
    order = client.post(
        "/bulk-orders", json=_order_payload([{"package_id": str(package.id), "quantity": 3}]), headers=auth_headers(consumer)
    ).json()
    assert client.get(f"/bulk-orders/{order['id']}", headers=auth_headers(other)).status_code == 404
    assert client.get("/admin/bulk-orders", headers=auth_headers(consumer)).status_code == 403
    assert len(client.get("/bulk-orders", headers=auth_headers(consumer)).json()) == 1


def test_custom_design_booking_uses_package_band(client, db, consumer, artist_with_profile, package):
    _, artist_profile = artist_with_profile
    upload = client.post(
        "/bookings/reference-image", files={"file": ("mine.png", _png(), "image/png")}, headers=auth_headers(consumer)
    )
    assert upload.status_code == 200
    url = upload.json()["url"]
    assert url.startswith("/media/references/")

    payload = {
        "artist_id": str(artist_profile.user_id),
        "package_id": str(package.id),
        "location_lat": 28.6,
        "location_lng": 77.2,
        "scheduled_at": _event_at(),
        "reference_design_image_url": url,
        "opening_offer": 5000,  # above the package's 1000-3000 band
    }
    assert client.post("/bookings", json=payload, headers=auth_headers(consumer)).status_code == 400
    payload["opening_offer"] = 2000
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 200
    assert res.json()["reference_design_image_url"] == url
    assert (res.json()["package_price_min"], res.json()["package_price_max"]) == (1000, 3000)
