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


def test_reference_image_rejects_external_url(client, consumer, artist_with_profile, package):
    """A consumer-supplied external URL here would be fetched server-side to
    score design similarity - allowing one would be an SSRF vector (e.g.
    pointing at a cloud metadata endpoint). Must be rejected at the schema
    layer before it ever reaches the filesystem/network code."""
    _, artist_profile = artist_with_profile
    payload = _booking_payload(artist_profile, package, reference_design_image_url="http://169.254.169.254/latest/meta-data/")
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 422


def test_reference_image_rejects_path_traversal(client, consumer, artist_with_profile, package):
    _, artist_profile = artist_with_profile
    payload = _booking_payload(artist_profile, package, reference_design_image_url="/media/../../../etc/passwd")
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 422


def test_reference_image_accepts_local_upload_path(client, consumer, artist_with_profile, package):
    _, artist_profile = artist_with_profile
    payload = _booking_payload(artist_profile, package, reference_design_image_url="/media/designs/abc123.jpg")
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 200


def test_payment_get_blocks_other_consumers(client, db, consumer, artist_with_profile, package):
    """IDOR check: GET /bookings/{id}/payment must only be readable by the
    consumer who owns that booking, not any other authenticated consumer."""
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    other_consumer = make_user(db, role="consumer")
    res = client.get(f"/bookings/{booking_id}/payment", headers=auth_headers(other_consumer))
    assert res.status_code == 404


def test_me_profile_endpoint_is_scoped_by_token_not_client_input(client, db, artist_with_profile):
    """/artists/me/profile is scoped entirely by the caller's JWT - there's
    no id parameter a caller could tamper with to read someone else's
    profile, and a consumer token must be rejected outright."""
    artist_user, _ = artist_with_profile
    res = client.get("/artists/me/profile", headers=auth_headers(artist_user))
    assert res.status_code == 200
    assert res.json()["user_id"] == str(artist_user.id)

    consumer = make_user(db, role="consumer")
    res2 = client.get("/artists/me/profile", headers=auth_headers(consumer))
    assert res2.status_code == 403


def test_negotiation_offer_amount_is_bounded(client, consumer, artist_with_profile, package):
    _, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    res = client.post(f"/bookings/{booking_id}/offers", json={"amount": 5_000_000}, headers=auth_headers(consumer))
    assert res.status_code == 422

    res2 = client.post(f"/bookings/{booking_id}/offers", json={"amount": -100}, headers=auth_headers(consumer))
    assert res2.status_code == 422
