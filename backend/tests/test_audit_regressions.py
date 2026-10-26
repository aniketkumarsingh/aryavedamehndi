"""Regression tests for issues found in the payments & orders audit."""

from app.database import SessionLocal
from app.models.job import Job
from app.models.notification import Notification
from app.services import email as email_service, jobs
from tests.conftest import auth_headers, make_user, run_jobs
from tests.test_orders_payments import _place, gst_seller  # noqa: F401 - fixture
from tests.test_razorpay_webhook import _send, webhook_secret  # noqa: F401 - fixture
from tests.test_shop import _make_product, _pay


def _paid_order(client, db, consumer, price=100, stock=5):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=price, stock=stock)
    order = _place(client, consumer, product).json()
    rp = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).json()["razorpay_order_id"]
    return admin, product, order, rp


def test_second_different_payment_is_flagged_not_overwritten(client, db, consumer):
    admin, _, order, rp = _paid_order(client, db, consumer)
    _send(client, rp, payment_id="pay_first")
    run_jobs()
    _send(client, rp, payment_id="pay_second")
    run_jobs()
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["payment_status"] == "paid" and body["refunds"] == []
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Duplicate payment").count() == 1


def test_webhook_corrects_amount_after_browser_verify(client, db, consumer):
    _, _, order, rp = _paid_order(client, db, consumer)
    client.post(f"/shop/orders/{order['id']}/payment/verify",
                json={"razorpay_order_id": rp, "razorpay_payment_id": "pay_offer", "razorpay_signature": "dev"}, headers=auth_headers(consumer))
    _send(client, rp, payment_id="pay_offer", amount_paise=12900)  # Razorpay Offer applied
    run_jobs()
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["amount_paid"] == 129


def test_refund_before_dispatch_must_be_a_cancellation(client, db, consumer):
    admin, _, order, _ = _paid_order(client, db, consumer)
    _pay(client, consumer, order["id"])
    res = client.post(f"/admin/shop-orders/{order['id']}/refunds", json={"amount": 10, "reason": "Goodwill"}, headers=auth_headers(admin))
    assert res.status_code == 400 and "cancel it instead" in res.json()["detail"]


def test_returned_cod_parcel_restocks_and_voids(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=2)
    order = _place(client, consumer, product, payment_method="cod").json()
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    res = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "returned", "reason": "Refused at door"}, headers=auth_headers(admin)).json()
    assert res["status"] == "returned" and res["payment_status"] == "void"
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 2


def test_returned_prepaid_parcel_is_refunded_with_credit_note(client, db, consumer, gst_seller):  # noqa: F811
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=500, stock=2)
    client.put(f"/shop/products/{product['id']}", json={"name": product["name"], "price": 500, "hsn_code": "3305", "gst_rate": 18}, headers=auth_headers(admin))
    order = _place(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "returned"}, headers=auth_headers(admin))
    run_jobs()
    body = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert body["status"] == "returned" and body["payment_status"] == "refunded"
    assert body["refunds"][0]["credit_note_number"].startswith("CN")
    # A delivered order can't be marked returned through this flow.
    assert client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "delivered"}, headers=auth_headers(admin)).status_code == 400


def test_jobs_are_claimed_one_at_a_time(db):
    seen = {}

    @jobs.job_handler("test.peek")
    def peek(session, payload):
        others = session.query(Job).filter(Job.kind == "test.peek", Job.payload["n"].astext != payload["n"]).all()
        seen[payload["n"]] = [o.status for o in others]

    with SessionLocal() as s:
        jobs.enqueue(s, "test.peek", {"n": "a"})
        jobs.enqueue(s, "test.peek", {"n": "b"})
        s.commit()
    run_jobs()
    # While the first ran, the second was still waiting in the queue.
    first = next(k for k, v in seen.items() if v == ["queued"])
    assert first in ("a", "b")


def test_smtp_port_465_uses_implicit_tls(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls.append(type(self).__name__)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, **kwargs):
            calls.append("starttls")

        def login(self, *args):
            pass

        def send_message(self, msg):
            calls.append("sent")

    class SMTP_SSL(FakeSMTP):
        pass

    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", SMTP_SSL)
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.zoho.in")
    monkeypatch.setattr(email_service.settings, "smtp_port", 465)
    monkeypatch.setattr(email_service.settings, "smtp_from", "orders@example.com")
    email_service.send_email("a@b.co", "s", "t", "<p>h</p>")
    assert calls == ["SMTP_SSL", "sent"]
