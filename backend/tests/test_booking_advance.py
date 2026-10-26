from app.models.availability import ArtistAvailability
from tests.conftest import auth_headers, make_package


def _booking_payload(artist_profile, package, **overrides):
    payload = {
        "artist_id": str(artist_profile.user_id),
        "package_id": str(package.id),
        "address_text": "12 MG Road, Delhi",
        "location_lat": 28.6,
        "location_lng": 77.2,
        "scheduled_at": "2026-11-01T10:00:00",
    }
    payload.update(overrides)
    return payload


def _confirm_booking(client, consumer, artist_user, booking_id, amount=2500):
    offer_res = client.post(f"/bookings/{booking_id}/offers", json={"amount": amount}, headers=auth_headers(consumer))
    offer_id = offer_res.json()["id"]
    return client.post(
        f"/bookings/{booking_id}/offers/{offer_id}/respond", json={"action": "accept"}, headers=auth_headers(artist_user)
    )


def _pay_advance(client, consumer, booking_id):
    order_res = client.post(f"/bookings/{booking_id}/advance/order", headers=auth_headers(consumer))
    rp_order_id = order_res.json()["razorpay_order_id"]
    return client.post(
        f"/bookings/{booking_id}/advance/verify",
        json={"razorpay_order_id": rp_order_id, "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )


def test_booking_with_zero_advance_package_is_not_gated(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=0)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    assert create_res.json()["advance_status"] == "not_required"
    booking_id = create_res.json()["id"]

    _confirm_booking(client, consumer, artist_user, booking_id, amount=1500)
    enroute_res = client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))
    assert enroute_res.status_code == 200
    assert enroute_res.json()["status"] == "artist_enroute"


def test_booking_with_advance_blocks_enroute_until_paid(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    body = create_res.json()
    assert body["advance_status"] == "pending"
    assert body["advance_amount"] == 1000
    booking_id = body["id"]

    _confirm_booking(client, consumer, artist_user, booking_id)

    blocked_res = client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))
    assert blocked_res.status_code == 400

    pay_res = _pay_advance(client, consumer, booking_id)
    assert pay_res.json()["advance_status"] == "paid"
    assert pay_res.json()["advance_paid_at"] is not None

    enroute_res = client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))
    assert enroute_res.status_code == 200


def test_advance_refunded_on_early_cancel(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    _pay_advance(client, consumer, booking_id)

    # Still "confirmed" - artist hasn't left yet - so cancelling now must refund.
    cancel_res = client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer))
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["advance_status"] == "refund_pending"

    # The refund is tracked and goes through the queue to Razorpay; the
    # advance only reads "refunded" once Razorpay has processed it.
    from app.models.payment_ops import Refund
    from tests.conftest import run_jobs

    refund = db.query(Refund).one()
    assert refund.target_type == "booking_advance" and refund.status == "pending"
    run_jobs()
    db.expire_all()
    assert db.get(Refund, refund.id).status == "processed"
    assert client.get(f"/bookings/{booking_id}", headers=auth_headers(consumer)).json()["advance_status"] == "refunded"


def test_advance_forfeited_on_cancel_after_artist_enroute(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    _pay_advance(client, consumer, booking_id)
    client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))

    cancel_res = client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer))
    assert cancel_res.status_code == 200
    assert cancel_res.json()["advance_status"] == "forfeited"


def test_cannot_pay_advance_twice(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    _pay_advance(client, consumer, booking_id)

    second_order_res = client.post(f"/bookings/{booking_id}/advance/order", headers=auth_headers(consumer))
    assert second_order_res.status_code == 400


def test_other_consumer_cannot_pay_someone_elses_advance(client, db, consumer, artist_with_profile):
    from tests.conftest import make_user

    artist_user, artist_profile = artist_with_profile
    package = make_package(db, advance_amount=1000)

    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)

    stranger = make_user(db, role="consumer")
    res = client.post(f"/bookings/{booking_id}/advance/order", headers=auth_headers(stranger))
    assert res.status_code == 404


def test_booking_against_open_slot_marks_it_booked_and_blocks_reuse(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    slot = ArtistAvailability(artist_id=artist_user.id, slot_date="2026-11-05", start_time="10:00:00", end_time="12:00:00")
    db.add(slot)
    db.commit()
    db.refresh(slot)

    res = client.post(
        "/bookings",
        json=_booking_payload(artist_profile, package, availability_slot_id=str(slot.id)),
        headers=auth_headers(consumer),
    )
    assert res.status_code == 200
    assert res.json()["availability_slot_id"] == str(slot.id)

    db.refresh(slot)
    assert slot.status == "booked"

    # A second consumer trying to book the now-"booked" slot must be rejected.
    from tests.conftest import make_user

    other_consumer = make_user(db, role="consumer")
    res2 = client.post(
        "/bookings",
        json=_booking_payload(artist_profile, package, availability_slot_id=str(slot.id)),
        headers=auth_headers(other_consumer),
    )
    assert res2.status_code == 400


def test_slot_reopens_on_early_cancel(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    slot = ArtistAvailability(artist_id=artist_user.id, slot_date="2026-11-05", start_time="10:00:00", end_time="12:00:00")
    db.add(slot)
    db.commit()
    db.refresh(slot)

    create_res = client.post(
        "/bookings",
        json=_booking_payload(artist_profile, package, availability_slot_id=str(slot.id)),
        headers=auth_headers(consumer),
    )
    booking_id = create_res.json()["id"]

    client.post(f"/bookings/{booking_id}/cancel", headers=auth_headers(consumer))
    db.refresh(slot)
    assert slot.status == "open"
