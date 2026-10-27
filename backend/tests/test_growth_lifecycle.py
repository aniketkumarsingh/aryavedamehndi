from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models.booking import Booking
from app.models.growth import CampaignSend, Cart, ConsentRecord, Occasion
from app.models.job import Job
from app.models.notification import Notification
from app.models.shop import ShopCoupon
from app.services import messaging
from tests.conftest import auth_headers, make_package, make_user, run_jobs
from tests.test_booking_advance import _booking_payload, _confirm_booking
from tests.test_orders_payments import ADDRESS
from tests.test_shop import _make_product, _pay


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


@pytest.fixture
def whatsapp(monkeypatch):
    sent = []

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            template = json["payload"]["template"]
            sent.append((template["name"], template["to_and_components"][0]["to"][0],
                         [c["value"] for c in template["to_and_components"][0]["components"].values()]))
            return FakeResponse()

    monkeypatch.setattr(messaging.settings, "msg91_auth_key", "key")
    monkeypatch.setattr(messaging.settings, "msg91_whatsapp_number", "919800000000")
    monkeypatch.setattr(messaging.httpx, "Client", FakeClient)
    return sent


def _order(client, consumer, product, **extra):
    body = {**ADDRESS, "items": [{"product_id": product["id"], "quantity": 1}], **extra}
    return client.post("/shop/orders", json=body, headers=auth_headers(consumer))


# --------------------------------------------------------------- whatsapp --

def test_transactional_whatsapp_follows_the_order(client, db, consumer, admin, whatsapp):
    product = _make_product(client, admin, price=100, stock=5)
    order = _order(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped", "courier_name": "Delhivery"}, headers=auth_headers(admin))
    run_jobs()
    names = [s[0] for s in whatsapp]
    assert names == ["order_confirmed", "order_shipped"]
    assert whatsapp[0][1] == f"91{consumer.phone}" and whatsapp[0][2][1] == f"#{order['id'][:8].upper()}"


def test_whatsapp_is_off_without_a_number(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=5)
    order = _order(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    assert db.query(Job).filter(Job.kind == "messaging.whatsapp").count() == 0


def test_promotions_need_consent_and_carry_unsubscribe(client, db, consumer, whatsapp):
    assert messaging.send_template(db, consumer, "cart_reminder", {"name": "P", "link": "x"}) is False
    messaging.set_marketing_consent(db, consumer, True, "test")
    db.commit()
    assert messaging.send_template(db, consumer, "cart_reminder", {"name": "P", "link": "x"}) is True
    db.commit()
    run_jobs()
    assert "/unsubscribe?u=" in whatsapp[-1][2][-1]


def test_checkout_opt_in_and_unsubscribe_link(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=5)
    _order(client, consumer, product, marketing_opt_in=True)
    db.refresh(consumer)
    assert consumer.marketing_opt_in
    assert client.get("/users/me", headers=auth_headers(consumer)).json()["marketing_opt_in"] is True

    token = messaging.unsubscribe_token(consumer.id)
    assert client.post("/marketing/unsubscribe", json={"u": str(consumer.id), "t": "forged"}).status_code == 400
    assert client.post("/marketing/unsubscribe", json={"u": str(consumer.id), "t": token}).json()["status"] == "unsubscribed"
    db.refresh(consumer)
    assert consumer.marketing_opt_in is False
    kinds = [(r.granted, r.source) for r in db.query(ConsentRecord).order_by(ConsentRecord.created_at)]
    assert kinds == [(True, "checkout"), (False, "unsubscribe_link")]


# ----------------------------------------------------------- abandoned cart --

def test_abandoned_cart_sequence_and_recovery(client, db, consumer, admin):
    from app.services.growth import abandoned_cart_job

    product = _make_product(client, admin, price=200, stock=5)
    line = [{"product_id": product["id"], "variant_id": None, "quantity": 1}]
    assert client.put("/shop/cart", json={"items": line}, headers=auth_headers(consumer)).status_code == 200
    assert client.get("/shop/cart", headers=auth_headers(consumer)).json()["items"][0]["product_id"] == product["id"]

    cart = db.get(Cart, consumer.id)
    cart.updated_at = utcnow() - timedelta(hours=3)
    db.commit()
    with db.begin_nested():
        assert abandoned_cart_job(db, {}) == "1 first reminders, 0 coupon reminders"
        assert abandoned_cart_job(db, {}) == "0 first reminders, 0 coupon reminders"
    db.commit()
    cart.last_reminded_at = utcnow() - timedelta(hours=25)
    db.commit()
    with db.begin_nested():
        assert abandoned_cart_job(db, {}) == "0 first reminders, 1 coupon reminders"
    db.commit()
    coupon = db.query(ShopCoupon).filter(ShopCoupon.user_id == consumer.id).one()
    assert coupon.discount_value == 5 and coupon.usage_limit == 1

    # The personal coupon is useless to anyone else.
    stranger = make_user(db, role="consumer")
    q = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "coupon_code": coupon.code}, headers=auth_headers(stranger)).json()
    assert q["coupon_error"] == "This coupon code isn't valid"

    order = _order(client, consumer, product, coupon_code=coupon.code).json()
    assert order["source"] == "abandoned_cart" and order["discount_amount"] == 10
    assert client.get("/shop/cart", headers=auth_headers(consumer)).json()["items"] == []


def test_editing_the_cart_restarts_reminders(client, db, consumer, admin):
    product = _make_product(client, admin, price=200, stock=5)
    client.put("/shop/cart", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(consumer))
    cart = db.get(Cart, consumer.id)
    cart.reminder_stage = 1
    db.commit()
    client.put("/shop/cart", json={"items": [{"product_id": product["id"], "quantity": 2}]}, headers=auth_headers(consumer))
    db.refresh(cart)
    assert cart.reminder_stage == 0
    assert client.put("/shop/cart", json={"items": [{"product_id": "nope", "quantity": 1}]}, headers=auth_headers(consumer)).status_code == 422


# --------------------------------------------------------------- occasions --

def test_occasion_nudges_reach_opted_in_past_customers_once(client, db, consumer, artist_with_profile, admin):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db)
    booking_id = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer)).json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    db.get(Booking, booking_id).status = "completed"
    other = make_user(db, role="consumer")  # never booked
    messaging.set_marketing_consent(db, consumer, True, "test")
    messaging.set_marketing_consent(db, other, True, "test")
    db.commit()

    res = client.post("/admin/growth/occasions", json={"name": "Karva Chauth", "occasion_date": str((utcnow() + timedelta(days=10)).date()), "lead_days": 12},
                      headers=auth_headers(admin))
    assert res.status_code == 200
    from app.services.growth import occasions_job

    with db.begin_nested():
        assert occasions_job(db, {}) == "1 nudges sent"
        assert occasions_job(db, {}) == "0 nudges sent"
    db.commit()
    note = db.query(Notification).filter(Notification.user_id == consumer.id, Notification.title == "Karva Chauth is coming up").one()
    assert note.link_url.startswith("/artists/")
    assert db.query(CampaignSend).count() == 1
    assert client.get("/admin/growth/occasions", headers=auth_headers(admin)).json()[0]["reached"] == 1
    assert db.query(Occasion).one().sent_at is not None
