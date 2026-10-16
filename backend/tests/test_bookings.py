from tests.conftest import auth_headers, make_approved_artist, make_user


def _booking_payload(artist_profile, package):
    return {
        "artist_id": str(artist_profile.user_id),
        "package_id": str(package.id),
        "address_text": "12 MG Road, Delhi",
        "location_lat": 28.6,
        "location_lng": 77.2,
        "scheduled_at": "2026-11-01T10:00:00",
    }


def test_create_booking_happy_path(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "requested"
    assert body["consumer_id"] == str(consumer.id)
    assert body["artist_id"] == str(artist_user.id)


def test_create_booking_rejects_unapproved_artist(client, db, consumer, package):
    unapproved_artist, _ = make_approved_artist(db)
    # flip it back to pending after creation
    from app.models.user import ArtistProfile

    profile = db.get(ArtistProfile, unapproved_artist.id)
    profile.kyc_status = "pending"
    db.commit()

    payload = _booking_payload(profile, package)
    res = client.post("/bookings", json=payload, headers=auth_headers(consumer))
    assert res.status_code == 400


def test_create_booking_enforces_gender_match_by_default(client, db, package):
    female_consumer = make_user(db, role="consumer", gender="female")
    male_artist, male_profile = make_approved_artist(db, gender="male")

    res = client.post("/bookings", json=_booking_payload(male_profile, package), headers=auth_headers(female_consumer))
    assert res.status_code == 400

    # Explicit override works.
    payload = _booking_payload(male_profile, package)
    payload["gender_preference"] = "any"
    res2 = client.post("/bookings", json=payload, headers=auth_headers(female_consumer))
    assert res2.status_code == 200


def test_negotiation_offer_and_accept_flow(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    offer_res = client.post(
        f"/bookings/{booking_id}/offers", json={"amount": 2500, "message": "Can you do 2500?"}, headers=auth_headers(consumer)
    )
    assert offer_res.status_code == 200
    offer_id = offer_res.json()["id"]

    accept_res = client.post(
        f"/bookings/{booking_id}/offers/{offer_id}/respond", json={"action": "accept"}, headers=auth_headers(artist_user)
    )
    assert accept_res.status_code == 200
    body = accept_res.json()
    assert body["status"] == "confirmed"
    assert body["agreed_price"] == 2500
    assert body["total_amount"] > body["agreed_price"]
    # Call masking gets provisioned once a booking is confirmed.
    assert body["masked_call_number"] is not None


def test_cannot_respond_to_own_offer(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    offer_res = client.post(f"/bookings/{booking_id}/offers", json={"amount": 2500}, headers=auth_headers(consumer))
    offer_id = offer_res.json()["id"]

    res = client.post(
        f"/bookings/{booking_id}/offers/{offer_id}/respond", json={"action": "accept"}, headers=auth_headers(consumer)
    )
    assert res.status_code == 400


def test_artist_can_accept_booking_directly_without_prior_offer(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    assert create_res.json()["status"] == "requested"

    # No offers exist yet - the artist should still be able to confirm
    # outright at a price they name.
    offers_res = client.get(f"/bookings/{booking_id}/offers", headers=auth_headers(artist_user))
    assert offers_res.json() == []

    accept_res = client.post(f"/bookings/{booking_id}/accept", json={"amount": 2200}, headers=auth_headers(artist_user))
    assert accept_res.status_code == 200
    body = accept_res.json()
    assert body["status"] == "confirmed"
    assert body["agreed_price"] == 2200
    assert body["masked_call_number"] is not None


def test_consumer_cannot_directly_accept_their_own_booking(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    res = client.post(f"/bookings/{booking_id}/accept", json={"amount": 2200}, headers=auth_headers(consumer))
    assert res.status_code == 403


def test_direct_accept_blocked_once_already_confirmed(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]
    client.post(f"/bookings/{booking_id}/accept", json={"amount": 2200}, headers=auth_headers(artist_user))

    res = client.post(f"/bookings/{booking_id}/accept", json={"amount": 2500}, headers=auth_headers(artist_user))
    assert res.status_code == 400


def test_direct_accept_supersedes_pending_offers(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    offer_res = client.post(f"/bookings/{booking_id}/offers", json={"amount": 1800}, headers=auth_headers(consumer))
    offer_id = offer_res.json()["id"]

    client.post(f"/bookings/{booking_id}/accept", json={"amount": 2200}, headers=auth_headers(artist_user))

    offers_after = client.get(f"/bookings/{booking_id}/offers", headers=auth_headers(consumer)).json()
    matching = [o for o in offers_after if o["id"] == offer_id][0]
    assert matching["status"] == "rejected"


def test_non_participant_cannot_view_booking(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    create_res = client.post("/bookings", json=_booking_payload(artist_profile, package), headers=auth_headers(consumer))
    booking_id = create_res.json()["id"]

    stranger = make_user(db, role="consumer")
    res = client.get(f"/bookings/{booking_id}", headers=auth_headers(stranger))
    assert res.status_code == 403
