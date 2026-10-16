from app.core.security import create_access_token
from tests.conftest import auth_headers, make_user


def _confirmed_booking(db, consumer, artist_user, artist_profile, package):
    from app.models.booking import Booking

    booking = Booking(
        consumer_id=consumer.id,
        artist_id=artist_user.id,
        package_id=package.id,
        location_lat=28.6,
        location_lng=77.2,
        scheduled_at="2026-11-01T10:00:00",
        status="confirmed",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def test_chat_rest_history_blocks_non_participants(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    booking = _confirmed_booking(db, consumer, artist_user, artist_profile, package)

    stranger = make_user(db, role="consumer")
    res = client.get(f"/bookings/{booking.id}/chat/messages", headers=auth_headers(stranger))
    assert res.status_code == 403

    ok_res = client.get(f"/bookings/{booking.id}/chat/messages", headers=auth_headers(consumer))
    assert ok_res.status_code == 200
    assert ok_res.json() == []


def test_chat_websocket_round_trip_and_persistence(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    booking = _confirmed_booking(db, consumer, artist_user, artist_profile, package)

    consumer_token = create_access_token(consumer.id, "consumer")
    artist_token = create_access_token(artist_user.id, "artist")

    with client.websocket_connect(f"/ws/bookings/{booking.id}/chat?token={consumer_token}") as consumer_ws:
        with client.websocket_connect(f"/ws/bookings/{booking.id}/chat?token={artist_token}") as artist_ws:
            consumer_ws.send_json({"body": "Hello, are you free Saturday?"})

            # Both sockets - including the sender's own - receive the message.
            echoed = consumer_ws.receive_json()
            received = artist_ws.receive_json()
            assert echoed["id"] == received["id"]
            assert received["body"] == "Hello, are you free Saturday?"
            assert received["sender_role"] == "consumer"

    history_res = client.get(f"/bookings/{booking.id}/chat/messages", headers=auth_headers(consumer))
    assert len(history_res.json()) == 1
    assert history_res.json()[0]["body"] == "Hello, are you free Saturday?"


def test_chat_websocket_rejects_missing_token(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    booking = _confirmed_booking(db, consumer, artist_user, artist_profile, package)

    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(f"/ws/bookings/{booking.id}/chat"):
            pass
        assert False, "expected the connection to be rejected"
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def test_chat_websocket_rejects_non_participant(client, db, consumer, artist_with_profile, package):
    artist_user, artist_profile = artist_with_profile
    booking = _confirmed_booking(db, consumer, artist_user, artist_profile, package)
    stranger = make_user(db, role="consumer")
    stranger_token = create_access_token(stranger.id, "consumer")

    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(f"/ws/bookings/{booking.id}/chat?token={stranger_token}"):
            pass
        assert False, "expected the connection to be rejected"
    except WebSocketDisconnect as exc:
        assert exc.code == 4403
