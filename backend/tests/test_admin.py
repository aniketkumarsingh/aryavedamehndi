from tests.conftest import auth_headers, make_user


def test_admin_routes_reject_non_admin(client, consumer):
    res = client.get("/admin/overview", headers=auth_headers(consumer))
    assert res.status_code == 403


def test_admin_users_pagination(client, db):
    admin = make_user(db, role="admin", name="Admin")
    for _ in range(5):
        make_user(db, role="consumer")

    page1 = client.get("/admin/users", params={"limit": 2, "offset": 0}, headers=auth_headers(admin))
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get("/admin/users", params={"limit": 2, "offset": 2}, headers=auth_headers(admin))
    assert len(page2.json()) == 2
    assert {u["id"] for u in page1.json()}.isdisjoint({u["id"] for u in page2.json()})


def test_admin_users_limit_is_capped(client, db):
    admin = make_user(db, role="admin")
    res = client.get("/admin/users", params={"limit": 5000}, headers=auth_headers(admin))
    assert res.status_code == 422


def test_admin_suspend_and_reactivate_user(client, db):
    admin = make_user(db, role="admin")
    target = make_user(db, role="consumer")

    suspend_res = client.post(f"/admin/users/{target.id}/suspend", headers=auth_headers(admin))
    assert suspend_res.status_code == 200
    assert suspend_res.json()["is_active"] is False

    reactivate_res = client.post(f"/admin/users/{target.id}/reactivate", headers=auth_headers(admin))
    assert reactivate_res.json()["is_active"] is True


def test_admin_cannot_suspend_another_admin(client, db):
    admin = make_user(db, role="admin")
    other_admin = make_user(db, role="admin")
    res = client.post(f"/admin/users/{other_admin.id}/suspend", headers=auth_headers(admin))
    assert res.status_code == 400
