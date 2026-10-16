from tests.conftest import auth_headers, make_approved_artist, make_user


def test_list_all_artists_includes_stats(client, db):
    admin = make_user(db, role="admin")
    artist_user, _ = make_approved_artist(db)

    res = client.get("/admin/artists", headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["user_id"] == str(artist_user.id)
    assert body[0]["completed_bookings"] == 0
    assert body[0]["total_earnings"] == 0
    assert body[0]["is_suspended"] is False


def test_list_artists_rejects_non_admin(client, db, consumer):
    res = client.get("/admin/artists", headers=auth_headers(consumer))
    assert res.status_code == 403


def test_suspend_artist_removes_from_nearby_search_but_keeps_account_active(client, db):
    admin = make_user(db, role="admin")
    artist_user, artist_profile = make_approved_artist(db, lat=28.6, lng=77.2)

    suspend_res = client.post(f"/admin/artists/{artist_user.id}/suspend", headers=auth_headers(admin))
    assert suspend_res.status_code == 200
    assert suspend_res.json()["is_suspended"] is True
    assert suspend_res.json()["is_active"] is True  # account itself isn't locked

    nearby_res = client.get("/artists/nearby", params={"lat": 28.6, "lng": 77.2, "radius_km": 50})
    ids = [a["user_id"] for a in nearby_res.json()]
    assert str(artist_user.id) not in ids

    reactivate_res = client.post(f"/admin/artists/{artist_user.id}/reactivate", headers=auth_headers(admin))
    assert reactivate_res.json()["is_suspended"] is False

    nearby_res2 = client.get("/artists/nearby", params={"lat": 28.6, "lng": 77.2, "radius_km": 50})
    ids2 = [a["user_id"] for a in nearby_res2.json()]
    assert str(artist_user.id) in ids2


def test_artist_filter_by_kyc_status(client, db):
    admin = make_user(db, role="admin")
    make_approved_artist(db)  # kyc_status="approved"

    pending_res = client.get("/admin/artists", params={"status_filter": "pending"}, headers=auth_headers(admin))
    assert pending_res.json() == []

    approved_res = client.get("/admin/artists", params={"status_filter": "approved"}, headers=auth_headers(admin))
    assert len(approved_res.json()) == 1
