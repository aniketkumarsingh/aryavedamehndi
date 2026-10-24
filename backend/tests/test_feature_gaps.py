from io import BytesIO

from PIL import Image

from app.models.booking import Booking
from app.models.user import User
from app.services.storage import sign_media_url
from tests.conftest import auth_headers, make_package, make_user

BOOKING_LAT, BOOKING_LNG = 28.6, 77.2


def _png_bytes(color=(120, 40, 30)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def _create(client, consumer, artist_profile, package, **extra):
    payload = {
        "artist_id": str(artist_profile.user_id),
        "package_id": str(package.id),
        "address_text": "12 MG Road, Delhi",
        "location_lat": BOOKING_LAT,
        "location_lng": BOOKING_LNG,
        "scheduled_at": "2026-11-01T10:00:00",
        **extra,
    }
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _advance_to(client, consumer, artist_user, booking_id, stage, price=2000):
    """Walks a booking forward through the happy path up to `stage`."""
    order = ["confirmed", "artist_enroute", "arrived", "in_progress", "design_uploaded"]
    a, c = auth_headers(artist_user), auth_headers(consumer)
    assert client.post(f"/bookings/{booking_id}/accept", json={"amount": price}, headers=a).status_code == 200
    booking = client.get(f"/bookings/{booking_id}", headers=c).json()
    if booking["advance_status"] == "pending":
        adv = client.post(f"/bookings/{booking_id}/advance/order", headers=c).json()
        client.post(
            f"/bookings/{booking_id}/advance/verify",
            json={"razorpay_order_id": adv["razorpay_order_id"], "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
            headers=c,
        )
    steps = {
        "artist_enroute": lambda: client.post(f"/bookings/{booking_id}/enroute", headers=a),
        "arrived": lambda: client.post(f"/bookings/{booking_id}/arrived", params={"lat": BOOKING_LAT, "lng": BOOKING_LNG}, headers=a),
        "in_progress": lambda: client.post(f"/bookings/{booking_id}/start", headers=a),
        "design_uploaded": lambda: client.post(
            f"/bookings/{booking_id}/design-upload", files={"file": ("d.png", _png_bytes(), "image/png")}, headers=a
        ),
    }
    for step in order[1 : order.index(stage) + 1]:
        res = steps[step]()
        assert res.status_code == 200, (step, res.text)


def _pay(client, consumer, booking_id):
    c = auth_headers(consumer)
    order = client.post(f"/bookings/{booking_id}/payment/order", headers=c)
    assert order.status_code == 200, order.text
    return order.json()


# ---------------------------------------------------------- #1 state order --

def test_arrived_and_start_require_the_previous_step(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    a = auth_headers(artist_user)

    res = client.post(f"/bookings/{booking_id}/arrived", params={"lat": BOOKING_LAT, "lng": BOOKING_LNG}, headers=a)
    assert res.status_code == 400
    assert client.post(f"/bookings/{booking_id}/start", headers=a).status_code == 400

    _advance_to(client, consumer, artist_user, booking_id, "confirmed")
    assert client.post(f"/bookings/{booking_id}/start", headers=a).status_code == 400


def test_cancelled_booking_cannot_be_revived(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer))
    a = auth_headers(artist_user)
    assert client.post(f"/bookings/{booking_id}/start", headers=a).status_code == 400
    assert client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer)).status_code == 400


# ---------------------------------------------------------- #2 price band --

def test_offers_and_accepts_must_be_inside_the_price_band(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)  # band 1000-3000

    low = client.post(f"/bookings/{booking_id}/offers", json={"amount": 999}, headers=auth_headers(consumer))
    assert low.status_code == 400
    high = client.post(f"/bookings/{booking_id}/accept", json={"amount": 3001}, headers=auth_headers(artist_user))
    assert high.status_code == 400
    ok = client.post(f"/bookings/{booking_id}/offers", json={"amount": 1000}, headers=auth_headers(consumer))
    assert ok.status_code == 200


def test_opening_offer_outside_band_is_rejected(client, db, consumer, artist_with_profile):
    _, profile = artist_with_profile
    package = make_package(db)
    payload = {
        "artist_id": str(profile.user_id),
        "package_id": str(package.id),
        "location_lat": BOOKING_LAT,
        "location_lng": BOOKING_LNG,
        "scheduled_at": "2026-11-01T10:00:00",
        "opening_offer": 50,
    }
    assert client.post("/bookings", json=payload, headers=auth_headers(consumer)).status_code == 400


def test_non_negotiable_package_blocks_offers_but_allows_accept(client, db, consumer, artist_with_profile):
    artist_user, profile = artist_with_profile
    package = make_package(db)
    package.negotiable = False
    db.commit()
    booking_id = _create(client, consumer, profile, package)

    assert client.post(f"/bookings/{booking_id}/offers", json={"amount": 1500}, headers=auth_headers(consumer)).status_code == 400
    assert client.post(f"/bookings/{booking_id}/accept", json={"amount": 1500}, headers=auth_headers(artist_user)).status_code == 200


# -------------------------------------------------------- #3 advance credit --

def test_advance_is_credited_against_the_fee(client, db, consumer, artist_with_profile):
    artist_user, profile = artist_with_profile
    package = make_package(db, advance_amount=50)
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded", price=2000)  # fee 10% = 200
    client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": True}, headers=auth_headers(consumer))

    booking = client.get(f"/bookings/{booking_id}", headers=auth_headers(consumer)).json()
    assert booking["payment_breakdown"]["in_app_due"] == 150
    assert booking["payment_breakdown"]["artist_direct_due"] == 2000

    order = _pay(client, consumer, booking_id)
    assert order["amount"] == 150
    assert order["already_paid"] is False


def test_advance_larger_than_fee_completes_without_checkout(client, db, consumer, artist_with_profile):
    artist_user, profile = artist_with_profile
    package = make_package(db, advance_amount=500)
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded", price=2000)
    client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": True}, headers=auth_headers(consumer))

    order = _pay(client, consumer, booking_id)
    assert order["already_paid"] is True
    assert order["amount"] == 0

    booking = client.get(f"/bookings/{booking_id}", headers=auth_headers(consumer)).json()
    assert booking["status"] == "completed"
    # 500 advance - 200 fee = 300 of the artist's money held by the platform,
    # so the consumer pays the artist 300 less directly.
    assert booking["payment_breakdown"]["platform_owes_artist"] == 300
    assert booking["payment_breakdown"]["artist_direct_due"] == 1700
    payment = client.get(f"/bookings/{booking_id}/payment", headers=auth_headers(consumer)).json()
    assert payment["status"] == "paid"
    assert payment["platform_owes_artist"] == 300


def test_full_escrow_charge_subtracts_advance(client, db, consumer, artist_with_profile):
    artist_user, profile = artist_with_profile
    profile.razorpay_linked_account_id = "acc_dev_test"
    db.commit()
    package = make_package(db, advance_amount=100)
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded", price=2000)
    client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": True}, headers=auth_headers(consumer))

    order = _pay(client, consumer, booking_id)
    assert order["is_full_escrow"] is True
    assert order["amount"] == 2000 + 200 - 100


# ------------------------------------------- #19 confirm/verify guards --

def test_design_confirm_only_once_and_verify_is_idempotent(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded")
    c = auth_headers(consumer)
    assert client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": True}, headers=c).status_code == 200
    assert client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": False}, headers=c).status_code == 400

    order = _pay(client, consumer, booking_id)
    verify_body = {"razorpay_order_id": order["razorpay_order_id"], "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"}
    first = client.post(f"/bookings/{booking_id}/payment/verify", json=verify_body, headers=c)
    second = client.post(f"/bookings/{booking_id}/payment/verify", json=verify_body, headers=c)
    assert first.status_code == second.status_code == 200
    assert client.post(f"/bookings/{booking_id}/payment/order", headers=c).status_code == 400


# ------------------------------------------------ #4/#5/#12 disputes --

def test_report_only_disputes_after_arrival(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    c = auth_headers(consumer)

    client.post(f"/bookings/{booking_id}/report", json={"category": "other"}, headers=c)
    assert client.get(f"/bookings/{booking_id}", headers=c).json()["status"] == "requested"

    _advance_to(client, consumer, artist_user, booking_id, "in_progress")
    client.post(f"/bookings/{booking_id}/report", json={"category": "misconduct"}, headers=c)
    assert client.get(f"/bookings/{booking_id}", headers=c).json()["status"] == "disputed"


def test_report_category_is_validated(client, consumer, artist_with_profile, package):
    _, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    res = client.post(f"/bookings/{booking_id}/report", json={"category": "spam"}, headers=auth_headers(consumer))
    assert res.status_code == 400


def test_admin_releases_dispute_so_consumer_can_pay(client, db, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    admin = make_user(db, role="admin")
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded")
    client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": False}, headers=auth_headers(consumer))

    disputes = client.get("/admin/disputes", headers=auth_headers(admin)).json()
    assert [d["booking"]["id"] for d in disputes] == [booking_id]
    assert disputes[0]["completed_image_url"]

    res = client.post(
        f"/admin/bookings/{booking_id}/resolve-dispute", json={"outcome": "released", "notes": "Design matches"}, headers=auth_headers(admin)
    )
    assert res.status_code == 200
    assert res.json()["booking"]["status"] == "design_uploaded"
    assert res.json()["match_status"] == "consumer_confirmed"
    _pay(client, consumer, booking_id)


def test_admin_cancels_dispute_and_refunds_advance(client, db, consumer, artist_with_profile):
    artist_user, profile = artist_with_profile
    admin = make_user(db, role="admin")
    package = make_package(db, advance_amount=300)
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "in_progress")
    client.post(f"/bookings/{booking_id}/report", json={"category": "safety"}, headers=auth_headers(consumer))

    res = client.post(f"/admin/bookings/{booking_id}/resolve-dispute", json={"outcome": "cancelled"}, headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["booking"]["status"] == "cancelled"
    assert body["advance_status"] == "refunded"
    assert all(r["status"] == "resolved" for r in body["reports"])

    again = client.post(f"/admin/bookings/{booking_id}/resolve-dispute", json={"outcome": "released"}, headers=auth_headers(admin))
    assert again.status_code == 400


def test_disputed_booking_cannot_be_cancelled_by_parties(client, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "arrived")
    client.post(f"/bookings/{booking_id}/report", json={"category": "misconduct"}, headers=auth_headers(consumer))
    assert client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer)).status_code == 400


# -------------------------------------------------- #8/#9 geo audit --

def test_far_check_in_is_flagged_and_admin_notified(client, db, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    admin = make_user(db, role="admin")
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "artist_enroute")

    # ~5.5 km north of the booking address
    res = client.post(f"/bookings/{booking_id}/arrived", params={"lat": BOOKING_LAT + 0.05, "lng": BOOKING_LNG}, headers=auth_headers(artist_user))
    assert res.status_code == 200
    assert res.json()["arrival_flagged"] is True
    assert res.json()["arrival_distance_m"] > 5000

    flagged = client.get("/admin/bookings", params={"flagged_only": True}, headers=auth_headers(admin)).json()
    assert [b["id"] for b in flagged] == [booking_id]
    notes = client.get("/notifications", headers=auth_headers(admin)).json()
    assert any("far from" in n["title"] for n in (notes["items"] if isinstance(notes, dict) else notes))


def test_near_check_in_is_not_flagged_and_check_out_is_logged(client, db, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "in_progress")
    booking = db.get(Booking, booking_id)
    db.refresh(booking)
    assert booking.arrival_flagged is False

    res = client.post(
        f"/bookings/{booking_id}/design-upload",
        params={"lat": 28.6001, "lng": 77.2001},
        files={"file": ("d.png", _png_bytes(), "image/png")},
        headers=auth_headers(artist_user),
    )
    assert res.status_code == 200
    db.refresh(booking)
    assert (booking.artist_completed_lat, booking.artist_completed_lng) == (28.6001, 77.2001)


# ---------------------------------------------------- #11 settings --

def test_admin_settings_change_fee_and_strikes(client, db, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    admin = make_user(db, role="admin")
    assert client.get("/admin/settings", headers=auth_headers(consumer)).status_code == 403

    res = client.put("/admin/settings", json={"platform_fee_mode": "flat", "platform_fee_flat": 99}, headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["platform_fee_flat"] == 99
    assert client.put("/admin/settings", json={"design_match_threshold": 150}, headers=auth_headers(admin)).status_code == 422

    booking_id = _create(client, consumer, profile, package)
    confirmed = client.post(f"/bookings/{booking_id}/accept", json={"amount": 2000}, headers=auth_headers(artist_user)).json()
    assert confirmed["platform_fee"] == 99


# --------------------------------------------------- #7 refresh --

def test_refresh_token_rotates_and_replay_revokes_everything(client, db):
    phone = "9876500001"
    code = client.post("/auth/request-otp", json={"phone": phone}).json()["dev_otp"]
    login = client.post("/auth/verify-otp", json={"phone": phone, "code": code})
    assert login.status_code == 200
    first = login.json()["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first
    assert client.get("/users/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}).status_code == 200

    # Replaying the used token kills the whole family, including `second`.
    assert client.post("/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_access_token_cannot_be_used_as_refresh(client, consumer):
    token = auth_headers(consumer)["Authorization"].split()[1]
    assert client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_logout_revokes_refresh_token(client, db, consumer):
    from app.services.auth_tokens import issue_token_pair

    _, refresh = issue_token_pair(db, consumer)
    db.commit()
    assert client.post("/auth/logout", json={"refresh_token": refresh}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


# ---------------------------------------------------- #13 private KYC --

def test_kyc_documents_need_a_signed_url(client, db, artist_with_profile):
    artist_user, profile = artist_with_profile
    res = client.post(
        "/artists/me/kyc-selfie", files={"file": ("s.png", _png_bytes(), "image/png")}, headers=auth_headers(artist_user)
    )
    assert res.status_code == 200
    signed = res.json()["kyc_selfie_url"]
    assert "sig=" in signed
    path = signed.split("?")[0]

    assert client.get(signed).status_code == 200
    for bypass in (path, path.replace("/media/kyc/", "/media//kyc/"), path.replace("/media/kyc/", "/media/./kyc/"), path.replace("kyc", "KYC")):
        assert client.get(bypass).status_code == 404, bypass
    tampered = signed[:-4] + "0000"
    assert client.get(tampered).status_code == 404

    me = client.get("/artists/me/profile", headers=auth_headers(artist_user)).json()
    assert me["kyc_selfie_url"].startswith(path + "?")


def test_public_media_still_served_without_signature(client, artist_with_profile):
    artist_user, _ = artist_with_profile
    res = client.post("/artists/me/portfolio", files={"file": ("p.png", _png_bytes(), "image/png")}, headers=auth_headers(artist_user))
    assert res.status_code == 200
    urls = res.json()["portfolio_urls"].split(",")
    assert urls[0].startswith("/media/portfolio/")
    assert client.get(urls[0]).status_code == 200
    assert sign_media_url(urls[0]) == urls[0]


# ------------------------------------------------- #14 two-way rating --

def test_artist_review_updates_consumer_rating(client, db, consumer, artist_with_profile, package):
    artist_user, profile = artist_with_profile
    booking_id = _create(client, consumer, profile, package)
    _advance_to(client, consumer, artist_user, booking_id, "design_uploaded")
    client.post(f"/bookings/{booking_id}/design-confirm", json={"satisfied": True}, headers=auth_headers(consumer))
    order = _pay(client, consumer, booking_id)
    client.post(
        f"/bookings/{booking_id}/payment/verify",
        json={"razorpay_order_id": order["razorpay_order_id"], "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )

    assert client.post(f"/bookings/{booking_id}/review", json={"rating": 4}, headers=auth_headers(artist_user)).status_code == 200
    db.refresh(db.get(User, consumer.id))
    assert db.get(User, consumer.id).consumer_rating_count == 1

    next_booking = _create(client, consumer, profile, package)
    seen_by_artist = client.get(f"/bookings/{next_booking}", headers=auth_headers(artist_user)).json()
    assert seen_by_artist["consumer_rating_avg"] == 4
    assert seen_by_artist["consumer_rating_count"] == 1
    assert seen_by_artist["package_duration_minutes"] == 120


# ------------------------------------------------------ #21 CMS history --

def test_cms_saves_history_and_restores(client, db):
    admin = make_user(db, role="admin", name="Asha")
    h = auth_headers(admin)
    client.put("/cms/home.hero", json={"content": {"title": "v1"}}, headers=h)
    client.put("/cms/home.hero", json={"content": {"title": "v2"}}, headers=h)

    versions = client.get("/cms/home.hero/versions", headers=h).json()
    assert [v["content"]["title"] for v in versions] == ["v2", "v1"]
    assert versions[0]["updated_by"] == "Asha"

    restored = client.post(f"/cms/home.hero/versions/{versions[1]['id']}/restore", headers=h)
    assert restored.json()["content"] == {"title": "v1"}
    assert client.get("/cms/home.hero").json()["content"] == {"title": "v1"}
    assert client.get("/cms/home.hero/versions", headers=auth_headers(make_user(db))).status_code == 403
