from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models.growth import ConversionEvent, Referral, WalletEntry
from app.models.job import Job
from app.models.shop import ShopOrder
from app.services import conversions, referrals
from tests.conftest import auth_headers, make_user, run_jobs
from tests.test_orders_payments import ADDRESS
from tests.test_shop import _make_product, _pay


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


def _order(client, user, product, qty=1, **extra):
    body = {**ADDRESS, "items": [{"product_id": product["id"], "quantity": qty}], **extra}
    return client.post("/shop/orders", json=body, headers=auth_headers(user))


def _deliver(client, admin, order_id):
    client.post(f"/admin/shop-orders/{order_id}/status", json={"status": "shipped", "courier_name": "X"}, headers=auth_headers(admin))
    client.post(f"/admin/shop-orders/{order_id}/status", json={"status": "delivered"}, headers=auth_headers(admin))


def _age_delivery(db, order_id, days=8):
    db.get(ShopOrder, order_id).delivered_at = utcnow() - timedelta(days=days)
    db.commit()


def test_referral_end_to_end(client, db, consumer, admin):
    product = _make_product(client, admin, price=300, stock=20)
    me = client.get("/users/me/referral", headers=auth_headers(consumer)).json()
    assert me["code"] and me["link"].endswith(f"?ref={me['code']}") and me["friend_discount"] == 50

    friend = make_user(db, role="consumer")
    assert client.post("/users/me/referral/apply", json={"code": "NOPE1234"}, headers=auth_headers(friend)).status_code == 400
    assert client.post("/users/me/referral/apply", json={"code": me["code"]}, headers=auth_headers(consumer)).status_code == 400  # own code
    assert client.post("/users/me/referral/apply", json={"code": me["code"]}, headers=auth_headers(friend)).json()["status"] == "applied"
    assert client.post("/users/me/referral/apply", json={"code": me["code"]}, headers=auth_headers(friend)).status_code == 400  # once

    quote = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(friend)).json()
    assert quote["referral_discount"] == 50 and quote["total_amount"] == 300 - 50 + 49  # below free delivery
    order = _order(client, friend, product).json()
    assert order["referral_discount"] == 50 and order["source"] == "referral" and order["discount_amount"] == 50
    _pay(client, friend, order["id"])
    _deliver(client, admin, order["id"])

    from app.services.referrals import referral_rewards_job
    with db.begin_nested():
        assert referral_rewards_job(db, {}) == "0 referral rewards"  # return window still open
    db.commit()
    _age_delivery(db, order["id"])
    with db.begin_nested():
        assert referral_rewards_job(db, {}) == "1 referral rewards"
    db.commit()
    assert referrals.balance(db, consumer.id) == 50
    me = client.get("/users/me/referral", headers=auth_headers(consumer)).json()
    assert me["invited"] == 1 and me["rewarded"] == 1 and me["earned"] == 50

    # Second order: no more friend discount.
    q2 = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(friend)).json()
    assert q2["referral_discount"] == 0


def test_cancelled_first_order_frees_the_discount_and_return_voids_reward(client, db, consumer, admin):
    product = _make_product(client, admin, price=300, stock=20)
    code = client.get("/users/me/referral", headers=auth_headers(consumer)).json()["code"]
    friend = make_user(db, role="consumer")
    client.post("/users/me/referral/apply", json={"code": code}, headers=auth_headers(friend))
    first = _order(client, friend, product).json()
    client.post(f"/shop/orders/{first['id']}/cancel", json={}, headers=auth_headers(friend))
    assert db.get(ShopOrder, first["id"]).status == "cancelled"
    second = _order(client, friend, product).json()
    assert second["referral_discount"] == 50

    _pay(client, friend, second["id"])
    _deliver(client, admin, second["id"])
    order = client.get(f"/shop/orders/{second['id']}", headers=auth_headers(friend)).json()
    import json as _json
    client.post(f"/shop/orders/{second['id']}/returns", headers=auth_headers(friend),
                data={"items": _json.dumps([{"order_item_id": order["items"][0]["id"], "quantity": 1}]), "reason_code": "changed_mind"})
    referral = db.query(Referral).filter(Referral.referee_id == friend.id).one()
    db.refresh(referral)
    assert referral.status == "void"


def test_wallet_fifo_cap_restore_and_expiry(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=20)
    soon = referrals.add_credit(db, consumer.id, 30, "Promo", days=10)
    later = referrals.add_credit(db, consumer.id, 200, "Promo", days=100)
    db.commit()
    assert client.get("/users/me/wallet", headers=auth_headers(consumer)).json()["balance"] == 230

    q = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "use_wallet": True}, headers=auth_headers(consumer)).json()
    assert q["wallet_amount"] == 99 and q["wallet_balance"] == 230  # items stay at ₹1
    order = _order(client, consumer, product, use_wallet=True).json()
    assert order["wallet_amount"] == 99 and order["total_amount"] == 1 + 49
    db.refresh(soon), db.refresh(later)
    assert soon.remaining == 0 and later.remaining == 131  # soonest-expiring first

    client.post(f"/shop/orders/{order['id']}/cancel", json={}, headers=auth_headers(consumer))
    db.refresh(soon), db.refresh(later)
    assert soon.remaining == 30 and later.remaining == 200
    kinds = [e["kind"] for e in client.get("/users/me/wallet", headers=auth_headers(consumer)).json()["entries"]]
    assert "spend" in kinds and "restore" in kinds

    soon.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    with db.begin_nested():
        assert referrals.wallet_expiry_job(db, {}) == "1 credits expired"
    db.commit()
    assert referrals.balance(db, consumer.id) == 200
    assert db.query(WalletEntry).filter(WalletEntry.kind == "expire").one().amount == -30


def test_attribution_and_ref_capture(client, db, consumer, admin):
    code = client.get("/users/me/referral", headers=auth_headers(consumer)).json()["code"]
    friend = make_user(db, role="consumer")
    res = client.post("/growth/attribution", headers=auth_headers(friend),
                      json={"utm_source": "instagram", "utm_campaign": "diwali", "ref": code, "analytics_consent": True}).json()
    assert res["referral"] == "applied"
    client.post("/growth/attribution", headers=auth_headers(friend), json={"utm_source": "google"})  # first touch kept
    db.refresh(friend)
    assert friend.attribution["utm_source"] == "instagram" and friend.analytics_consent

    product = _make_product(client, admin, price=100, stock=5)
    order = _order(client, consumer, product, attribution={"utm_source": "Newsletter", "gclid": "abc"}).json()
    assert order["source"] == "newsletter"
    assert db.get(ShopOrder, order["id"]).attribution["gclid"] == "abc"


def test_server_conversions_need_consent_and_send_once(client, db, consumer, admin, monkeypatch):
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

        def post(self, url, params=None, json=None):
            sent.append((url, json))
            return FakeResponse()

    for key, value in (("meta_pixel_id", "123"), ("meta_capi_token", "tok"), ("ga4_measurement_id", "G-1"), ("ga4_api_secret", "sec")):
        monkeypatch.setattr(conversions.settings, key, value)
    monkeypatch.setattr(conversions.httpx, "Client", FakeClient)
    product = _make_product(client, admin, price=100, stock=5)

    order = _order(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    assert db.query(Job).filter(Job.kind == "conversions.purchase").count() == 0  # no consent, nothing queued

    consumer.analytics_consent = True
    db.commit()
    order = _order(client, consumer, product, payment_method="cod").json()
    run_jobs()
    assert len(sent) == 2
    meta = next(j for u, j in sent if "facebook" in u)["data"][0]
    assert meta["event_id"] == order["id"] and meta["user_data"]["ph"][0] != consumer.phone  # hashed
    ga = next(j for u, j in sent if "google" in u)
    assert ga["events"][0]["params"]["transaction_id"] == order["id"]
    conversions.send_purchase(db, {"order_id": order["id"]})
    assert len(sent) == 2 and db.query(ConversionEvent).count() == 2


def test_growth_dashboard_and_csv(client, db, consumer, admin):
    product = _make_product(client, admin, price=200, stock=5)
    _order(client, consumer, product, attribution={"utm_source": "instagram"})
    data = client.get("/admin/growth/dashboard", params={"weeks": 4}, headers=auth_headers(admin)).json()
    this_week = data["weeks"][-1]
    assert len(data["weeks"]) == 4 and this_week["shop_orders"] == 1 and this_week["sources"] == {"instagram": 1}
    assert this_week["new_customers"] >= 1
    csv_text = client.get("/admin/growth/dashboard.csv", headers=auth_headers(admin)).text
    assert csv_text.splitlines()[0].startswith("week_start,new_customers") and "source:instagram" in csv_text
    assert client.get("/admin/growth/dashboard", headers=auth_headers(consumer)).status_code == 403
