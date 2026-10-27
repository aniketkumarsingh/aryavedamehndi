import io

import pytest
from PIL import Image

from app.models.catalog import Design
from tests.conftest import auth_headers, make_package, make_user
from tests.test_orders_payments import _place
from tests.test_shop import _pay
from tests.test_returns_and_sla import _delivered


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (90, 140, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _review(client, user, product_id, rating, photos=0, **extra):
    files = [("photos", (f"r{i}.png", _png(), "image/png")) for i in range(photos)]
    return client.post(f"/shop/products/{product_id}/reviews", data={"rating": rating, **extra}, files=files or None,
                       headers=auth_headers(user))


def test_only_buyers_with_a_delivered_order_can_review(client, db, consumer, admin):
    product, _ = _delivered(client, db, consumer, admin, qty=1)
    stranger = make_user(db, role="consumer")
    assert _review(client, stranger, product["id"], 5).status_code == 400
    assert client.get(f"/shop/products/{product['id']}/reviews/mine", headers=auth_headers(stranger)).json()["can_review"] is False
    assert client.get(f"/shop/products/{product['id']}/reviews/mine", headers=auth_headers(consumer)).json()["can_review"] is True

    assert _review(client, consumer, product["id"], 6).status_code == 400
    first = _review(client, consumer, product["id"], 4, photos=1, title="Lovely colour", body="Dark stain after a night")
    assert first.status_code == 200 and first.json()["photo_urls"] and first.json()["author"]
    again = _review(client, consumer, product["id"], 2, body="Faded in a week")  # posting again edits it
    assert again.json()["id"] == first.json()["id"] and again.json()["photo_urls"] == first.json()["photo_urls"]

    listing = client.get(f"/shop/products/{product['id']}/reviews").json()
    assert listing["rating_count"] == 1 and listing["rating_avg"] == 2 and listing["breakdown"]["2"] == 1
    assert client.get(f"/shop/products/{product['id']}").json()["rating_count"] == 1


def test_admin_hiding_a_review_updates_the_rating(client, db, consumer, admin):
    product, _ = _delivered(client, db, consumer, admin, qty=1)
    other = make_user(db, role="consumer")
    order = _place(client, other, product, qty=1).json()
    _pay(client, other, order["id"])
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped", "courier_name": "X"}, headers=auth_headers(admin))
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "delivered"}, headers=auth_headers(admin))

    _review(client, consumer, product["id"], 5)
    spam = _review(client, other, product["id"], 1, body="visit my site").json()
    assert client.get(f"/shop/products/{product['id']}").json()["rating_avg"] == 3
    res = client.post(f"/admin/product-reviews/{spam['id']}/status", json={"status": "hidden"}, headers=auth_headers(admin))
    assert res.status_code == 200
    body = client.get(f"/shop/products/{product['id']}/reviews").json()
    assert body["rating_avg"] == 5 and body["rating_count"] == 1 and len(body["reviews"]) == 1
    assert _review(client, other, product["id"], 5).status_code == 400  # hidden reviews stay hidden
    assert client.get("/admin/product-reviews", params={"status": "hidden"}, headers=auth_headers(admin)).json()[0]["product_name"]
    assert client.get("/admin/product-reviews", headers=auth_headers(consumer)).status_code == 403


def test_artist_portfolio_only_for_verified_artists(client, db, artist_with_profile):
    artist_user, profile = artist_with_profile
    profile.kyc_status = "pending"
    db.commit()
    assert client.get(f"/artists/by-slug/{profile.slug}").status_code == 404
    profile.kyc_status, profile.city = "approved", "Jaipur"
    db.commit()
    page = client.get(f"/artists/by-slug/{profile.slug}")
    assert page.status_code == 200 and page.json()["city"] == "Jaipur" and page.json()["name"] == artist_user.name
    assert "phone" not in page.json()
    assert profile.slug in [e["slug"] for e in client.get("/artists/sitemap").json()]
    profile.is_suspended = True
    db.commit()
    assert client.get(f"/artists/by-slug/{profile.slug}").status_code == 404


def test_artist_can_set_city(client, db, artist_with_profile):
    artist_user, profile = artist_with_profile
    me = client.get("/artists/me/profile", headers=auth_headers(artist_user)).json()
    body = {k: me.get(k) for k in ("bio", "service_radius_km", "address_text", "base_lat", "base_lng")}
    res = client.put("/artists/me/profile", json={**body, "city": " Lucknow "}, headers=auth_headers(artist_user))
    assert res.status_code == 200 and res.json()["city"] == "Lucknow" and res.json()["slug"]


def test_landing_pages(client, db, admin, artist_with_profile):
    _, profile = artist_with_profile
    profile.kyc_status, profile.city = "approved", "Jaipur"
    package = make_package(db)
    db.add(Design(package_id=package.id, name="Bridal Full Hands", price_min=2000, price_max=5000, occasions=["bridal"], is_active=True))
    db.add(Design(package_id=package.id, name="Simple Arabic", price_min=300, price_max=600, occasions=["festival"], is_active=True))
    db.commit()

    assert client.put("/admin/landing-pages/Bad Slug", json={"title": "x" * 5, "heading": "y" * 5}, headers=auth_headers(admin)).status_code == 400
    saved = client.put("/admin/landing-pages/bridal-mehndi-jaipur", headers=auth_headers(admin), json={
        "title": "Bridal Mehndi Artists in Jaipur", "heading": "Bridal mehndi in Jaipur", "intro": "Verified artists at home.",
        "city": "jaipur", "occasion": "bridal"})
    assert saved.status_code == 200
    page = client.get("/landing-pages/bridal-mehndi-jaipur").json()
    assert [a["slug"] for a in page["artists"]] == [profile.slug]
    assert [d["name"] for d in page["designs"]] == ["Bridal Full Hands"]
    assert client.get("/landing-pages").json()[0]["slug"] == "bridal-mehndi-jaipur"

    client.put("/admin/landing-pages/bridal-mehndi-jaipur", headers=auth_headers(admin), json={
        "title": "Bridal Mehndi Artists in Jaipur", "heading": "Bridal mehndi in Jaipur", "is_active": False})
    assert client.get("/landing-pages/bridal-mehndi-jaipur").status_code == 404
    assert client.delete("/admin/landing-pages/bridal-mehndi-jaipur", headers=auth_headers(admin)).json()["status"] == "deleted"
