from tests.conftest import auth_headers, make_approved_artist


def test_favorite_add_list_remove(client, db, consumer):
    artist_user, _ = make_approved_artist(db)

    add_res = client.post(f"/favorites/{artist_user.id}", headers=auth_headers(consumer))
    assert add_res.status_code == 204

    list_res = client.get("/favorites", headers=auth_headers(consumer))
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["artist_id"] == str(artist_user.id)

    del_res = client.delete(f"/favorites/{artist_user.id}", headers=auth_headers(consumer))
    assert del_res.status_code == 204

    list_res2 = client.get("/favorites", headers=auth_headers(consumer))
    assert list_res2.json() == []


def test_favorite_add_is_idempotent(client, db, consumer):
    """Favoriting the same artist twice is a harmless no-op (204 again),
    not an error - and must not create a second row."""
    artist_user, _ = make_approved_artist(db)
    client.post(f"/favorites/{artist_user.id}", headers=auth_headers(consumer))
    res = client.post(f"/favorites/{artist_user.id}", headers=auth_headers(consumer))
    assert res.status_code == 204

    list_res = client.get("/favorites", headers=auth_headers(consumer))
    assert len(list_res.json()) == 1


def test_notifications_pagination(client, db, consumer):
    from app.services.notifications import notify

    for i in range(5):
        notify(db, consumer.id, "system", f"Notice {i}")
    db.commit()

    page1 = client.get("/notifications", params={"limit": 2, "offset": 0}, headers=auth_headers(consumer))
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get("/notifications", params={"limit": 2, "offset": 2}, headers=auth_headers(consumer))
    assert len(page2.json()) == 2
    assert {m["id"] for m in page1.json()}.isdisjoint({m["id"] for m in page2.json()})

    over_limit = client.get("/notifications", params={"limit": 999}, headers=auth_headers(consumer))
    assert over_limit.status_code == 422


def test_unread_count_and_mark_read(client, db, consumer):
    from app.services.notifications import notify

    notify(db, consumer.id, "system", "Hello")
    db.commit()

    count_res = client.get("/notifications/unread-count", headers=auth_headers(consumer))
    assert count_res.json()["unread_count"] == 1

    mark_res = client.post("/notifications/read-all", headers=auth_headers(consumer))
    assert mark_res.status_code == 204

    count_res2 = client.get("/notifications/unread-count", headers=auth_headers(consumer))
    assert count_res2.json()["unread_count"] == 0
