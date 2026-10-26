"""Cash on Delivery, idempotent checkout, partial refunds, invoices and
credit notes, emails, reconciliation and the admin payments summary."""

import uuid
from datetime import timedelta

import pytest

from app.models.payment_ops import ReconciliationRun
from app.models.shop import ShopOrder
from app.services import documents, email as email_service, razorpay_client
from tests.conftest import auth_headers, make_user, run_jobs
from tests.test_shop import _make_product, _pay

ADDRESS = {"shipping_name": "Priya", "shipping_phone": "9812345680", "shipping_address": "12 MG Road", "shipping_state": "Delhi", "shipping_pincode": "110001"}


def _place(client, consumer, product, qty=1, headers=None, **extra):
    body = {**ADDRESS, "items": [{"product_id": product["id"], "quantity": qty}], **extra}
    return client.post("/shop/orders", json=body, headers={**auth_headers(consumer), **(headers or {})})


@pytest.fixture
def admin(db):
    return make_user(db, role="admin")


# ------------------------------------------------------------------- COD --

def test_cod_order_is_confirmed_at_once_with_fee(client, db, consumer, admin):
    product = _make_product(client, admin, price=200, stock=5)
    q = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "cod"}, headers=auth_headers(consumer)).json()
    assert q["cod_available"] and q["cod_fee"] == 30 and q["total_amount"] == 279  # 200 + 49 delivery + 30 COD

    order = _place(client, consumer, product, payment_method="cod").json()
    assert (order["status"], order["payment_method"], order["payment_status"]) == ("confirmed", "cod", "cod_due")
    assert order["total_amount"] == 279 and order["cod_fee"] == 30
    assert client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer)).status_code == 400

    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    delivered = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "delivered"}, headers=auth_headers(admin)).json()
    assert delivered["payment_status"] == "cod_collected" and delivered["amount_paid"] == 279


def test_cod_limits(client, db, consumer, admin):
    pricey = _make_product(client, admin, price=3000, stock=5, name="Bridal box")
    cheap = _make_product(client, admin, price=100, stock=10, name="Cone")
    q = client.post("/shop/quote", json={"items": [{"product_id": pricey["id"], "quantity": 1}], "payment_method": "cod"}, headers=auth_headers(consumer)).json()
    assert not q["cod_available"] and "up to ₹2500" in q["cod_error"] and q["cod_fee"] == 0
    assert _place(client, consumer, pricey, payment_method="cod").status_code == 400

    assert _place(client, consumer, cheap, payment_method="cod").status_code == 200
    assert _place(client, consumer, cheap, payment_method="cod").status_code == 200
    third = _place(client, consumer, cheap, payment_method="cod")
    assert third.status_code == 400 and "already have Cash on Delivery orders" in third.json()["detail"]

    client.put("/admin/settings", json={"shop_cod_enabled": False}, headers=auth_headers(admin))
    assert "isn't available" in client.post("/shop/quote", json={"items": [{"product_id": cheap["id"], "quantity": 1}], "payment_method": "cod"}, headers=auth_headers(consumer)).json()["cod_error"]


def test_cancelling_cod_order_voids_it_without_refund(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=3)
    order = _place(client, consumer, product, payment_method="cod").json()
    res = client.post(f"/shop/orders/{order['id']}/cancel", json={}, headers=auth_headers(consumer)).json()
    assert res["status"] == "cancelled" and res["payment_status"] == "void" and res["refunds"] == []
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 3


# ---------------------------------------------------------- idempotency --

def test_same_idempotency_key_returns_the_same_order(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=5)
    key = {"Idempotency-Key": str(uuid.uuid4())}
    first = _place(client, consumer, product, headers=key)
    second = _place(client, consumer, product, headers=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert db.query(ShopOrder).count() == 1
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 4

    reused = _place(client, consumer, product, qty=2, headers=key)
    assert reused.status_code == 409

    # Without a key, each request is a new order.
    _place(client, consumer, product)
    assert db.query(ShopOrder).count() == 2


def test_failed_request_frees_its_idempotency_key(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=1)
    key = {"Idempotency-Key": "retry-me"}
    assert _place(client, consumer, product, qty=2, headers=key).status_code == 400  # not enough stock
    fixed = _place(client, consumer, product, qty=1, headers=key)  # corrected retry with the same key
    assert fixed.status_code == 200
    assert _place(client, consumer, product, qty=1, headers=key).json()["id"] == fixed.json()["id"]
    assert _place(client, consumer, product, qty=2, headers=key).status_code == 409  # key now belongs to that order


# ---------------------------------------------------- refunds & documents --

@pytest.fixture
def gst_seller(monkeypatch):
    for key, value in {"business_legal_name": "AryaVeda Naturals Pvt Ltd", "business_state": "Delhi", "business_gstin": "07ABCDE1234F1Z5",
                       "business_address": "1 Henna Lane, New Delhi"}.items():
        monkeypatch.setattr(documents.settings, key, value)


def _taxed_product(client, admin, price=100, stock=10):
    product = _make_product(client, admin, price=price, stock=stock)
    client.put(f"/shop/products/{product['id']}", json={"name": product["name"], "price": price, "hsn_code": "3305", "gst_rate": 18}, headers=auth_headers(admin))
    return product


def test_receipt_then_tax_invoice_then_credit_note(client, db, consumer, admin, gst_seller):
    product = _taxed_product(client, admin, price=500)
    order = _place(client, consumer, product, qty=1).json()
    assert client.get(f"/shop/orders/{order['id']}/document", headers=auth_headers(consumer)).status_code == 400  # unpaid
    _pay(client, consumer, order["id"])

    receipt = client.get(f"/shop/orders/{order['id']}/document", headers=auth_headers(consumer)).json()
    assert receipt["kind"] == "receipt" and receipt["totals"]["total"] == 500  # free delivery at 500

    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    invoice = client.get(f"/shop/orders/{order['id']}/document", headers=auth_headers(consumer)).json()
    assert invoice["kind"] == "tax_invoice" and invoice["number"].startswith("AV") and invoice["intra_state"]
    assert invoice["totals"] == {"taxable": 423.73, "cgst": 38.14, "sgst": 38.13, "igst": 0.0, "total": 500.0}
    assert invoice["amount_in_words"] == "Rupees Five Hundred Only"
    pdf = client.get(f"/shop/orders/{order['id']}/document.pdf", headers=auth_headers(consumer))
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")

    # Partial refund for a damaged item -> credit note against the invoice.
    res = client.post(f"/admin/shop-orders/{order['id']}/refunds", json={"amount": 100, "reason": "Jar arrived cracked"}, headers=auth_headers(admin))
    assert res.status_code == 200 and res.json()["payment_status"] == "refund_pending"
    run_jobs()
    after = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()
    assert after["payment_status"] == "partially_refunded" and after["amount_refunded"] == 100
    refund = after["refunds"][0]
    assert refund["credit_note_number"].startswith("CN")
    note = client.get(f"/shop/refunds/{refund['id']}/credit-note", headers=auth_headers(consumer)).json()
    assert note["against"]["number"] == invoice["number"] and note["totals"]["total"] == 100
    assert round(note["totals"]["taxable"] + note["totals"]["cgst"] + note["totals"]["sgst"], 2) == 100
    assert client.get(f"/shop/refunds/{refund['id']}/credit-note.pdf", headers=auth_headers(consumer)).content.startswith(b"%PDF")

    # Can't refund more than what's left; the rest can still be refunded.
    assert client.post(f"/admin/shop-orders/{order['id']}/refunds", json={"amount": 450, "reason": "Too much"}, headers=auth_headers(admin)).status_code == 400
    assert client.post(f"/admin/shop-orders/{order['id']}/refunds", json={"amount": 400, "reason": "Goodwill"}, headers=auth_headers(admin)).status_code == 200
    run_jobs()
    assert client.get(f"/shop/orders/{order['id']}", headers=auth_headers(consumer)).json()["payment_status"] == "refunded"

    stranger = make_user(db, role="consumer")
    assert client.get(f"/shop/orders/{order['id']}/document.pdf", headers=auth_headers(stranger)).status_code == 403


def test_other_state_uses_igst_and_charges_take_highest_rate(client, db, consumer, admin, gst_seller):
    product = _taxed_product(client, admin, price=100)
    order = _place(client, consumer, product, qty=1, shipping_state="Maharashtra", payment_method="cod").json()
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    doc = client.get(f"/shop/orders/{order['id']}/document", headers=auth_headers(consumer)).json()
    assert not doc["intra_state"] and doc["totals"]["cgst"] == 0
    assert [line["description"] for line in doc["lines"]][1:] == ["Delivery charges", "Cash on Delivery charges"]
    assert all(line["rate"] == 18 for line in doc["lines"])
    assert doc["totals"]["total"] == 179


def test_rupees_in_words_indian_system():
    assert documents.rupees_in_words(0) == "Rupees Zero Only"
    assert documents.rupees_in_words(1234567.5) == "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paise Only"
    assert documents.rupees_in_words(25000000) == "Rupees Two Crore Fifty Lakh Only"


# ----------------------------------------------------------------- email --

def test_shipping_email_carries_the_invoice(client, db, consumer, admin, gst_seller, monkeypatch):
    sent = []
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(email_service.settings, "smtp_from", "AryaVeda <orders@test>")
    monkeypatch.setattr(email_service, "send_email", lambda to, subject, text, html, attachments=(): sent.append((to, subject, [a[0] for a in attachments], attachments)))

    product = _taxed_product(client, admin, price=500)
    order = _place(client, consumer, product, contact_email="priya@example.com").json()
    _pay(client, consumer, order["id"])
    client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped", "tracking_number": "DL1"}, headers=auth_headers(admin))
    run_jobs()

    subjects = [s[1] for s in sent]
    assert subjects[0] == "Order confirmed - AryaVeda Mehndi"
    shipped = next(s for s in sent if s[1].startswith("Shipped"))
    assert shipped[0] == "priya@example.com" and shipped[2][0].startswith("AV") and shipped[3][0][1].startswith(b"%PDF")


def test_email_is_skipped_without_address_or_smtp(client, db, consumer, admin):
    product = _make_product(client, admin, price=100, stock=5)
    order = _place(client, consumer, product).json()
    _pay(client, consumer, order["id"])
    assert run_jobs() >= 1  # confirmation email job ran and finished without sending
    assert _place(client, consumer, product, contact_email="not-an-email").status_code == 422


# -------------------------------------------------------- reconciliation --

def test_reconciliation_records_missed_payments_and_flags_issues(client, db, consumer, admin, monkeypatch):
    product = _make_product(client, admin, price=100, stock=5)
    missed = _place(client, consumer, product).json()
    rp_missed = client.post(f"/shop/orders/{missed['id']}/payment/order", headers=auth_headers(consumer)).json()["razorpay_order_id"]
    held = _place(client, consumer, product).json()
    _pay(client, consumer, held["id"])
    row = db.get(ShopOrder, uuid.UUID(held["id"]))
    row.razorpay_payment_id = "pay_live_held"
    row.paid_at = row.paid_at - timedelta(hours=1)  # outside the 10-minute settling grace
    db.commit()

    monkeypatch.setattr(razorpay_client, "is_configured", lambda: True)
    monkeypatch.setattr(razorpay_client, "list_payments", lambda a, b: [
        {"id": "pay_live_missed", "order_id": rp_missed, "status": "captured", "amount": 14900},
        {"id": "pay_live_orphan", "order_id": "order_nobody", "status": "captured", "amount": 5000},
        {"id": "pay_live_held", "order_id": "order_x", "status": "failed", "amount": 14900},
    ])
    assert client.post("/admin/payments/reconciliation/run", headers=auth_headers(admin)).status_code == 202
    run_jobs()

    run = client.get("/admin/payments/reconciliation", headers=auth_headers(admin)).json()[0]
    assert run["status"] == "issues" and run["fixed"] == 1 and run["payments_seen"] == 3
    assert sorted(i["type"] for i in run["issues"]) == ["not_captured_at_gateway", "unmatched"]
    assert client.get(f"/shop/orders/{missed['id']}", headers=auth_headers(consumer)).json()["payment_status"] == "paid"


def test_reconciliation_is_skipped_in_dev_mode(db):
    from app.services.reconciliation import reconcile

    run = reconcile(db)
    assert run.status == "skipped"
    assert db.query(ReconciliationRun).count() == 1


# ----------------------------------------------------------- admin summary --

def test_payments_summary_flags_what_needs_attention(client, db, admin):
    from datetime import timedelta

    from app.core.time import utcnow
    from app.models.job import Job

    db.add(Job(kind="jobs.cleanup", status="queued", run_at=utcnow() - timedelta(minutes=20), created_at=utcnow()))
    db.add(Job(kind="refunds.submit", status="dead", run_at=utcnow(), created_at=utcnow(), attempts=10, last_error="x"))
    db.commit()
    summary = client.get("/admin/payments/summary", headers=auth_headers(admin)).json()
    assert summary["dead_jobs"] == 1 and summary["oldest_queued_seconds"] >= 1200
    assert any("worker" in a for a in summary["alerts"]) and any("gave up" in a for a in summary["alerts"])
    assert client.get("/admin/payments/summary", headers=auth_headers(make_user(db))).status_code == 403
