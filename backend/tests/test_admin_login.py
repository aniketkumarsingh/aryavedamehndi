from app.core.security import hash_password
from tests.conftest import make_user


def _admin_with_password(db, username="adminUser", password="adminUser"):
    admin = make_user(db, role="admin", name="Admin")
    admin.username = username
    admin.password_hash = hash_password(password)
    db.commit()
    return admin


def test_admin_login_success(client, db):
    _admin_with_password(db)
    res = client.post("/auth/admin-login", json={"username": "adminUser", "password": "adminUser"})
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "admin"
    assert body["access_token"]


def test_admin_login_wrong_password(client, db):
    _admin_with_password(db)
    res = client.post("/auth/admin-login", json={"username": "adminUser", "password": "nope"})
    assert res.status_code == 401


def test_admin_login_unknown_username(client, db):
    res = client.post("/auth/admin-login", json={"username": "ghost", "password": "x"})
    assert res.status_code == 401


def test_admin_login_token_works_on_protected_admin_routes(client, db):
    _admin_with_password(db)
    login_res = client.post("/auth/admin-login", json={"username": "adminUser", "password": "adminUser"})
    token = login_res.json()["access_token"]
    res = client.get("/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_admin_login_locks_out_after_repeated_failures(client, db):
    _admin_with_password(db)
    for _ in range(5):
        res = client.post("/auth/admin-login", json={"username": "adminUser", "password": "wrong"})
        assert res.status_code == 401

    locked_res = client.post("/auth/admin-login", json={"username": "adminUser", "password": "adminUser"})
    assert locked_res.status_code == 429


def test_non_admin_user_cannot_login_via_password_even_with_matching_username(client, db):
    consumer = make_user(db, role="consumer")
    consumer.username = "sneaky"
    consumer.password_hash = hash_password("whatever")
    db.commit()

    res = client.post("/auth/admin-login", json={"username": "sneaky", "password": "whatever"})
    assert res.status_code == 401
