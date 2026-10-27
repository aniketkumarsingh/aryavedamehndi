from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models.booking import Booking
from app.models.chat import ChatMessage
from app.models.growth import Cart
from app.models.user import ArtistProfile
from app.services.storage import save_upload
from tests.conftest import auth_headers, make_package, make_user
from tests.test_booking_advance import _booking_payload, _confirm_booking
from tests.test_orders_payments import ADDRESS
from tests.test_returns_and_sla import _png
from tests.test_shop import _make_product


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


def _order(client, user, product, **extra):
    return client.post("/shop/orders", json={**ADDRESS, "items": [{"product_id": product["id"], "quantity": 1}], **extra}, headers=auth_headers(user)).json()


def test_admin_lists_show_and_filter_by_source(client, db, consumer, admin, artist_with_profile):
    product = _make_product(client, admin, price=100, stock=5)
    _order(client, consumer, product, attribution={"utm_source": "instagram"})
    _order(client, make_user(db, role="consumer"), product)  # no campaign: "direct"
    rows = client.get("/admin/shop-orders", params={"source": "instagram"}, headers=auth_headers(admin)).json()
    assert [r["source"] for r in rows] == ["instagram"]

    artist_user, profile = artist_with_profile
    package = make_package(db)
    payload = {**_booking_payload(profile, package), "attribution": {"utm_source": "google", "gclid": "x"}}
    assert client.post("/bookings", json=payload, headers=auth_headers(consumer)).status_code == 200
    bookings = client.get("/admin/bookings", params={"source": "google"}, headers=auth_headers(admin)).json()
    assert len(bookings) == 1 and bookings[0]["source"] == "google"


def test_dashboard_coupon_cost_referrals_and_cart_recovery(client, db, consumer, admin):
    from app.services.growth import abandoned_cart_job

    product = _make_product(client, admin, price=200, stock=20)
    client.post("/shop/admin/coupons", json={"code": "TEN", "discount_type": "flat", "discount_value": 10, "is_active": True},
                headers=auth_headers(admin))
    _order(client, consumer, product, coupon_code="TEN")

    code = client.get("/users/me/referral", headers=auth_headers(consumer)).json()["code"]
    friend = make_user(db, role="consumer")
    client.post("/users/me/referral/apply", json={"code": code}, headers=auth_headers(friend))
    client.put("/shop/cart", json={"items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(friend))
    cart = db.get(Cart, friend.id)
    cart.updated_at = utcnow() - timedelta(hours=3)
    db.commit()
    with db.begin_nested():
        abandoned_cart_job(db, {})
    db.commit()
    _order(client, friend, product)  # referral discount, and recovers the reminded cart

    week = client.get("/admin/growth/dashboard", params={"weeks": 1}, headers=auth_headers(admin)).json()["weeks"][-1]
    assert week["coupon_cost"] == 10
    assert week["referral_orders"] == 1 and week["referral_discounts"] == 50
    assert week["carts_reminded"] == 1 and week["cart_recovered"] == 1 and week["cart_recovery_rate"] == 100
    assert "cart_recovery_rate" in client.get("/admin/growth/dashboard.csv", headers=auth_headers(admin)).text.splitlines()[0]


def test_artist_page_lists_packages(client, db, artist_with_profile):
    _, profile = artist_with_profile
    package = make_package(db)
    page = client.get(f"/artists/by-slug/{profile.slug}").json()
    assert package.name in [p["name"] for p in page["packages"]]


def test_retention_clears_rejected_kyc_and_old_chat(client, db, consumer, admin, artist_with_profile, tmp_path, monkeypatch):
    from app.services import privacy, storage

    monkeypatch.setattr(storage, "MEDIA_DIR", tmp_path)
    artist_user, profile = artist_with_profile
    package = make_package(db)
    booking_id = client.post("/bookings", json=_booking_payload(profile, package), headers=auth_headers(consumer)).json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)

    doc = save_upload(_png(), "kyc")
    profile.id_proof_doc_url, profile.id_proof_number = doc, "1234-5678-9012"
    db.commit()
    client.post(f"/admin/artists/{artist_user.id}/kyc/reject", headers=auth_headers(admin))
    db.refresh(profile)
    assert profile.kyc_reviewed_at is not None
    db.add(ChatMessage(booking_id=booking_id, sender_id=consumer.id, sender_role="consumer", body="Gate code 1234"))
    booking = db.get(Booking, booking_id)
    booking.status = "completed"
    db.commit()

    with db.begin_nested():
        result = privacy.retention_job(db, {})
    assert "rejected_kyc 0" in result and "chat_messages 0" in result  # too recent

    profile.kyc_reviewed_at = utcnow() - timedelta(days=91)
    booking.scheduled_at = utcnow() - timedelta(days=181)
    db.commit()
    with db.begin_nested():
        result = privacy.retention_job(db, {})
    db.commit()
    assert "rejected_kyc 1" in result and "chat_messages 1" in result
    db.refresh(profile)
    assert profile.id_proof_doc_url is None and profile.id_proof_number is None
    assert not list(tmp_path.rglob("*.png")) and db.get(ArtistProfile, artist_user.id).kyc_status == "rejected"
