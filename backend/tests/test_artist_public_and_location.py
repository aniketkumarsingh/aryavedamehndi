from tests.conftest import auth_headers, make_user


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


def test_public_profile_excludes_sensitive_fields(client, db, consumer, artist_with_profile):
    artist_user, artist_profile = artist_with_profile
    res = client.get(f"/artists/{artist_user.id}/public-profile", headers=auth_headers(consumer))
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == artist_user.name
    assert "phone" not in body
    assert "bank_account_number" not in body
    assert "id_proof_doc_url" not in body
    assert "razorpay_linked_account_id" not in body


def test_public_profile_404_for_unknown_artist(client, consumer):
    import uuid

    res = client.get(f"/artists/{uuid.uuid4()}/public-profile", headers=auth_headers(consumer))
    assert res.status_code == 404


def test_location_update_rejected_before_enroute(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)

    res = client.post(f"/bookings/{booking_id}/location", json={"lat": 28.61, "lng": 77.21}, headers=auth_headers(artist_user))
    assert res.status_code == 400


def test_location_update_works_once_enroute_and_recomputes_eta(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))

    res = client.post(f"/bookings/{booking_id}/location", json={"lat": 28.61, "lng": 77.21}, headers=auth_headers(artist_user))
    assert res.status_code == 200
    body = res.json()
    assert body["artist_current_lat"] == 28.61
    assert body["artist_current_lng"] == 77.21
    assert body["artist_location_updated_at"] is not None
    assert body["eta_minutes"] is not None


def test_location_update_blocked_for_other_artist(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))

    other_artist = make_user(db, role="artist")
    res = client.post(f"/bookings/{booking_id}/location", json={"lat": 1, "lng": 1}, headers=auth_headers(other_artist))
    assert res.status_code == 403


def test_location_update_rejects_consumer_role(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    _confirm_booking(client, consumer, artist_user, booking_id)
    client.post(f"/bookings/{booking_id}/enroute", headers=auth_headers(artist_user))

    res = client.post(f"/bookings/{booking_id}/location", json={"lat": 1, "lng": 1}, headers=auth_headers(consumer))
    assert res.status_code == 403
