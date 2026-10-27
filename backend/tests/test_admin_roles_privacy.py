import io
from datetime import timedelta

import pytest
from PIL import Image

from app.core.time import utcnow
from app.models.admin_ops import AdminAuditLog
from app.models.growth import ConsentRecord
from app.models.otp import OtpCode
from app.models.shop import ShopOrder
from app.models.user import User
from tests.conftest import auth_headers, make_user
from tests.test_orders_payments import ADDRESS
from tests.test_shop import _make_product, _pay


@pytest.fixture
def owner(db):
    return make_user(db, role="admin")  # no admin_role yet = owner (as for existing admins)


def _admin(db, role):
    user = make_user(db, role="admin")
    user.admin_role = role
    db.commit()
    return user


# ------------------------------------------------------------------ roles --

def test_role_policy(client, db, owner):
    ops, support = _admin(db, "ops"), _admin(db, "support")
    settings = client.get("/admin/settings", headers=auth_headers(owner)).json()
    assert client.put("/admin/settings", json=settings, headers=auth_headers(owner)).status_code == 200
    assert client.get("/admin/settings", headers=auth_headers(ops)).status_code == 200
    denied = client.put("/admin/settings", json=settings, headers=auth_headers(ops))
    assert denied.status_code == 403 and "ops" in denied.json()["detail"]
    assert client.get("/admin/settings", headers=auth_headers(support)).status_code == 403

    assert client.get("/admin/shop-orders", headers=auth_headers(support)).status_code == 200  # read-only is fine
    assert client.get("/admin/payments/refunds", headers=auth_headers(support)).status_code == 403
    assert client.get("/admin/artists/pending-kyc", headers=auth_headers(support)).status_code == 403
    assert client.post("/admin/payments/reconciliation/run", headers=auth_headers(support)).status_code == 403
    assert client.get("/admin/team", headers=auth_headers(ops)).status_code == 403
    assert client.get("/admin/audit", headers=auth_headers(owner)).status_code == 200


def test_support_can_write_notes_and_everything_is_audited(client, db, owner, consumer):
    support = _admin(db, "support")
    product = _make_product(client, owner, price=100, stock=5)
    order = client.post("/shop/orders", json={**ADDRESS, "items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(consumer)).json()

    note = client.post("/admin/notes", json={"target_type": "shop_order", "target_id": order["id"], "body": "Customer called: wants Friday delivery"},
                       headers=auth_headers(support))
    assert note.status_code == 200 and note.json()["author"] == support.name
    notes = client.get("/admin/notes", params={"target_type": "shop_order", "target_id": order["id"]}, headers=auth_headers(owner)).json()
    assert [n["body"] for n in notes] == ["Customer called: wants Friday delivery"]
    assert client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "cancelled"}, headers=auth_headers(support)).status_code == 403
    assert client.get("/admin/notes", params={"target_type": "shop_order", "target_id": order["id"]}, headers=auth_headers(consumer)).status_code == 403

    rows = client.get("/admin/audit", headers=auth_headers(owner)).json()
    by_path = {(r["method"], r["path"], r["status_code"]) for r in rows}
    assert ("POST", "/admin/notes", 200) in by_path
    assert ("POST", f"/admin/shop-orders/{order['id']}/status", 403) in by_path
    assert all(r["request_id"] for r in rows)
    assert db.query(AdminAuditLog).filter(AdminAuditLog.method == "GET", AdminAuditLog.path == "/admin/notes").count() == 0  # reads aren't logged


def test_team_management_keeps_an_owner(client, db, owner):
    added = client.post("/admin/team", json={"phone": "9876500011", "name": "Ravi Ops", "admin_role": "ops"}, headers=auth_headers(owner))
    assert added.status_code == 200 and added.json()["admin_role"] == "ops"
    consumer = make_user(db, role="consumer")
    assert client.post("/admin/team", json={"phone": consumer.phone, "name": "X Y", "admin_role": "ops"}, headers=auth_headers(owner)).status_code == 400
    assert client.put(f"/admin/team/{owner.id}", json={"admin_role": "support"}, headers=auth_headers(owner)).status_code == 400  # last owner
    client.put(f"/admin/team/{added.json()['id']}", json={"admin_role": "owner"}, headers=auth_headers(owner))
    assert client.put(f"/admin/team/{owner.id}", json={"admin_role": "support"}, headers=auth_headers(owner)).json()["admin_role"] == "support"
    me = client.get("/users/me", headers=auth_headers(owner)).json()
    assert me["admin_role"] == "support"


# ------------------------------------------------------------------ media --

def test_uploads_become_webp_without_location_data(client, db, consumer):
    img = Image.new("RGB", (5000, 1000), (200, 120, 40))
    exif = Image.Exif()
    exif[0x8825] = {2: (28.0, 36.0, 0.0), 4: (77.0, 12.0, 0.0)}  # GPS
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    from app.services.storage import save_upload

    url = save_upload(buf.getvalue(), "avatars")
    assert url.endswith(".webp")
    res = client.get(url)
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    stored = Image.open(io.BytesIO(res.content))
    assert stored.format == "WEBP" and max(stored.size) == 4000 and not stored.getexif()


# ---------------------------------------------------------------- privacy --

def test_account_deletion(client, db, consumer, owner):
    product = _make_product(client, owner, price=100, stock=5)
    open_order = client.post("/shop/orders", json={**ADDRESS, "items": [{"product_id": product["id"], "quantity": 1}]}, headers=auth_headers(consumer)).json()
    _pay(client, consumer, open_order["id"])
    check = client.get("/users/me/deletion-check", headers=auth_headers(consumer)).json()
    assert check["can_delete"] is False and check["blocking"]
    assert client.post("/users/me/delete", json={"confirm": "DELETE"}, headers=auth_headers(consumer)).status_code == 400
    client.post(f"/admin/shop-orders/{open_order['id']}/status", json={"status": "shipped", "courier_name": "X"}, headers=auth_headers(owner))
    client.post(f"/admin/shop-orders/{open_order['id']}/status", json={"status": "delivered"}, headers=auth_headers(owner))

    export = client.get("/users/me/export", headers=auth_headers(consumer))
    assert export.status_code == 200 and export.json()["shop_orders"][0]["id"] == open_order["id"]

    phone = consumer.phone
    assert client.post("/users/me/delete", json={"confirm": "nope"}, headers=auth_headers(consumer)).status_code == 400
    done = client.post("/users/me/delete", json={"confirm": "delete"}, headers=auth_headers(consumer))
    assert done.status_code == 200
    db.expire_all()
    user = db.get(User, consumer.id)
    assert user.name == "Deleted user" and user.phone != phone and not user.is_active and user.deleted_at
    assert client.get("/users/me", headers=auth_headers(consumer)).status_code == 401
    order = db.get(ShopOrder, open_order["id"])
    assert order.invoice_number and order.shipping_name == ADDRESS["shipping_name"]  # GST invoice keeps billing details
    assert db.query(ConsentRecord).filter(ConsentRecord.user_id == consumer.id, ConsentRecord.source == "account_deleted").count() == 2
    # The number can sign up again as a new account.
    assert db.query(User).filter(User.phone == phone).count() == 0


def test_retention_job(db, consumer):
    from app.services.privacy import retention_job

    db.add(OtpCode(phone=consumer.phone, code="123456", expires_at=utcnow() - timedelta(days=2), created_at=utcnow() - timedelta(days=2)))
    db.commit()
    with db.begin_nested():
        result = retention_job(db, {})
    db.commit()
    assert "otp 1" in result and db.query(OtpCode).count() == 0
