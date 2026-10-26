from tests.conftest import auth_headers, make_user


def _make_product(client, admin, price=49, stock=10, name="Organic Mehndi Cone"):
    res = client.post(
        "/shop/products",
        json={"name": name, "description": "Natural henna cone", "price": price, "stock_quantity": stock},
        headers=auth_headers(admin),
    )
    assert res.status_code == 200
    return res.json()


def test_only_admin_can_create_products(client, db, consumer):
    admin = make_user(db, role="admin")
    res = client.post("/shop/products", json={"name": "x", "price": 10, "stock_quantity": 1}, headers=auth_headers(consumer))
    assert res.status_code == 403

    res2 = client.post("/shop/products", json={"name": "x", "price": 10, "stock_quantity": 1}, headers=auth_headers(admin))
    assert res2.status_code == 200


def test_public_product_list_excludes_inactive(client, db):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin)

    list_res = client.get("/shop/products")
    assert len(list_res.json()) == 1

    client.delete(f"/shop/products/{product['id']}", headers=auth_headers(admin))
    list_res2 = client.get("/shop/products")
    assert list_res2.json() == []


def test_create_order_decrements_stock_and_snapshots_price(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=49, stock=10)

    order_res = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya Verma",
            "shipping_phone": "9812345680",
            "shipping_address": "12 MG Road, Delhi",
            "items": [{"product_id": product["id"], "quantity": 3}],
        },
        headers=auth_headers(consumer),
    )
    assert order_res.status_code == 200
    body = order_res.json()
    # 147 of items is under the free-delivery amount, so the delivery charge applies.
    assert body["items_amount"] == 147
    assert body["shipping_fee"] == 49
    assert body["total_amount"] == 196
    assert body["status"] == "pending"
    assert body["items"][0]["unit_price"] == 49
    assert body["items"][0]["quantity"] == 3

    product_res = client.get(f"/shop/products/{product['id']}")
    assert product_res.json()["stock_quantity"] == 7


def test_order_rejected_when_stock_insufficient(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=49, stock=2)

    res = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya",
            "shipping_phone": "9812345680",
            "shipping_address": "Delhi",
            "items": [{"product_id": product["id"], "quantity": 5}],
        },
        headers=auth_headers(consumer),
    )
    assert res.status_code == 400

    # Stock must be untouched after a rejected order.
    product_res = client.get(f"/shop/products/{product['id']}")
    assert product_res.json()["stock_quantity"] == 2


def test_payment_order_and_verify_dev_mode(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=49, stock=10)

    order = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya",
            "shipping_phone": "9812345680",
            "shipping_address": "Delhi",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=auth_headers(consumer),
    ).json()

    pay_order_res = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer))
    assert pay_order_res.status_code == 200
    rp_order_id = pay_order_res.json()["razorpay_order_id"]
    assert rp_order_id.startswith("order_dev_")

    verify_res = client.post(
        f"/shop/orders/{order['id']}/payment/verify",
        json={"razorpay_order_id": rp_order_id, "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "paid"
    assert verify_res.json()["paid_at"] is not None


def test_order_is_not_visible_to_other_consumers(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin)
    order = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya",
            "shipping_phone": "9812345680",
            "shipping_address": "Delhi",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=auth_headers(consumer),
    ).json()

    stranger = make_user(db, role="consumer")
    res = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(stranger))
    assert res.status_code == 403

    admin_res = client.get(f"/shop/orders/{order['id']}", headers=auth_headers(admin))
    assert admin_res.status_code == 200


def test_admin_list_and_update_shop_order_status(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin)
    order = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya",
            "shipping_phone": "9812345680",
            "shipping_address": "Delhi",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=auth_headers(consumer),
    ).json()

    list_res = client.get("/admin/shop-orders", headers=auth_headers(admin))
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # An unpaid order can't be shipped.
    early = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    assert early.status_code == 400
    _pay(client, consumer, order["id"])

    ship_res = client.post(
        f"/admin/shop-orders/{order['id']}/status",
        json={"status": "shipped", "courier_name": "Delhivery", "tracking_number": "DL123", "tracking_url": "https://track.example/DL123"},
        headers=auth_headers(admin),
    )
    assert ship_res.status_code == 200
    assert ship_res.json()["status"] == "shipped"
    assert ship_res.json()["shipped_at"] is not None
    assert ship_res.json()["tracking_number"] == "DL123"

    # Shipped orders can't go backwards or be cancelled.
    assert client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "cancelled"}, headers=auth_headers(admin)).status_code == 400

    non_admin_res = client.get("/admin/shop-orders", headers=auth_headers(consumer))
    assert non_admin_res.status_code == 403


def test_invalid_order_status_rejected(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin)
    order = client.post(
        "/shop/orders",
        json={
            "shipping_name": "Priya",
            "shipping_phone": "9812345680",
            "shipping_address": "Delhi",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=auth_headers(consumer),
    ).json()

    res = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "teleported"}, headers=auth_headers(admin))
    assert res.status_code == 422


def _catalogue_product(db, requires_licence=True, licence_number=None, active=False):
    from app.models.shop import ShopProduct, ShopProductVariant

    product = ShopProduct(
        slug="natural-henna-powder", name="Natural Henna Powder", category="body-art", price=120, stock_quantity=0,
        requires_licence=requires_licence, licence_number=licence_number, is_active=active, image_kind="illustrative",
    )
    product.variants = [
        ShopProductVariant(label="100 g", price=120, stock_quantity=5, sort_order=0),
        ShopProductVariant(label="250 g", price=260, stock_quantity=2, sort_order=1),
        ShopProductVariant(label="1 kg", price=900, stock_quantity=9, sort_order=2, is_active=False),
    ]
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _order(client, consumer, items):
    return client.post(
        "/shop/orders",
        json={"shipping_name": "Priya", "shipping_phone": "9812345680", "shipping_address": "Delhi", "items": items},
        headers=auth_headers(consumer),
    )


def test_drafts_are_hidden_from_shoppers_but_listed_for_admin(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _catalogue_product(db)

    assert client.get("/shop/products").json() == []
    assert client.get(f"/shop/products/{product.id}").status_code == 404
    assert _order(client, consumer, [{"product_id": str(product.id), "variant_id": str(product.variants[0].id), "quantity": 1}]).status_code == 404

    admin_list = client.get("/shop/admin/products", headers=auth_headers(admin))
    assert admin_list.status_code == 200
    assert [p["slug"] for p in admin_list.json()] == ["natural-henna-powder"]
    assert client.get("/shop/admin/products", headers=auth_headers(consumer)).status_code == 403


def test_licensed_product_cannot_be_published_without_licence_number(client, db):
    admin = make_user(db, role="admin")
    product = _catalogue_product(db)

    res = client.post(f"/shop/products/{product.id}/publish", headers=auth_headers(admin))
    assert res.status_code == 400
    assert "licence" in res.json()["detail"]

    edit = client.put(
        f"/shop/products/{product.id}",
        json={"name": product.name, "price": 120, "licence_number": "AYUSH/MFG/2026/0001"},
        headers=auth_headers(admin),
    )
    assert edit.status_code == 200
    assert edit.json()["category"] == "body-art"  # a partial edit keeps the other details

    res = client.post(f"/shop/products/{product.id}/publish", headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["is_active"] is True

    # A live licensed product can't have its licence number removed.
    res = client.put(f"/shop/products/{product.id}", json={"name": product.name, "price": 120, "licence_number": ""}, headers=auth_headers(admin))
    assert res.status_code == 400


def test_new_licensed_product_starts_as_draft(client, db):
    admin = make_user(db, role="admin")
    res = client.post("/shop/products", json={"name": "Henna Hair Powder", "price": 199, "requires_licence": True}, headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_public_product_shows_active_variants_and_illustrative_label(client, db):
    product = _catalogue_product(db, licence_number="AYUSH/MFG/2026/0001", active=True)

    body = client.get(f"/shop/products/{product.id}").json()
    assert [v["label"] for v in body["variants"]] == ["100 g", "250 g"]
    assert body["image_kind"] == "illustrative"
    assert body["licence_number"] is None


def test_order_prices_and_stocks_by_variant(client, db, consumer):
    product = _catalogue_product(db, licence_number="AYUSH/MFG/2026/0001", active=True)
    small, large, retired = product.variants

    assert _order(client, consumer, [{"product_id": str(product.id), "quantity": 1}]).status_code == 400
    assert _order(client, consumer, [{"product_id": str(product.id), "variant_id": str(retired.id), "quantity": 1}]).status_code == 400
    assert _order(client, consumer, [{"product_id": str(product.id), "variant_id": str(large.id), "quantity": 3}]).status_code == 400

    res = _order(client, consumer, [{"product_id": str(product.id), "variant_id": str(large.id), "quantity": 2}])
    assert res.status_code == 200
    body = res.json()
    assert body["total_amount"] == 520
    assert body["items"][0]["variant_label"] == "250 g"
    assert body["items"][0]["unit_price"] == 260

    variants = {v["label"]: v for v in client.get(f"/shop/products/{product.id}").json()["variants"]}
    assert variants["250 g"]["stock_quantity"] == 0
    assert variants["100 g"]["stock_quantity"] == 5


def test_admin_sets_variant_stock(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _catalogue_product(db)
    variant = product.variants[0]

    assert client.put(f"/shop/variants/{variant.id}/stock", json={"stock_quantity": 40}, headers=auth_headers(consumer)).status_code == 403
    res = client.put(f"/shop/variants/{variant.id}/stock", json={"stock_quantity": 40}, headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["stock_quantity"] == 40


def _pay(client, consumer, order_id):
    rp = client.post(f"/shop/orders/{order_id}/payment/order", headers=auth_headers(consumer)).json()
    return client.post(
        f"/shop/orders/{order_id}/payment/verify",
        json={"razorpay_order_id": rp["razorpay_order_id"], "razorpay_payment_id": "dev_payment", "razorpay_signature": "dev"},
        headers=auth_headers(consumer),
    )


def _coupon(client, admin, **overrides):
    body = {"code": "henna10", "discount_type": "percent", "discount_value": 10, "max_discount": 100, "min_order_amount": 300}
    res = client.post("/shop/admin/coupons", json={**body, **overrides}, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    return res.json()


def test_coupon_discount_shipping_and_usage_limits(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=200, stock=20)
    coupon = _coupon(client, admin)
    assert coupon["code"] == "HENNA10"
    assert client.post("/shop/admin/coupons", json={"code": "HENNA10", "discount_type": "flat", "discount_value": 5}, headers=auth_headers(admin)).status_code == 400

    line = [{"product_id": product["id"], "quantity": 2}]
    # Below the minimum order the quote explains why, without failing.
    small = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "coupon_code": "henna10"}, headers=auth_headers(consumer)).json()
    assert small["discount_amount"] == 0 and "more to use this coupon" in small["coupon_error"]

    q = client.post("/shop/quote", json={"items": line, "coupon_code": " henna10 "}, headers=auth_headers(consumer)).json()
    assert (q["items_amount"], q["discount_amount"], q["shipping_fee"], q["total_amount"]) == (400, 40, 49, 409)

    res = client.post(
        "/shop/orders",
        json={"shipping_name": "Priya", "shipping_phone": "9812345680", "shipping_address": "Delhi", "items": line, "coupon_code": "HENNA10"},
        headers=auth_headers(consumer),
    )
    assert res.status_code == 200
    assert res.json()["total_amount"] == 409 and res.json()["coupon_code"] == "HENNA10"

    # Default per-user limit is 1.
    again = client.post(
        "/shop/orders",
        json={"shipping_name": "Priya", "shipping_phone": "9812345680", "shipping_address": "Delhi", "items": line, "coupon_code": "HENNA10"},
        headers=auth_headers(consumer),
    )
    assert again.status_code == 400 and "already used" in again.json()["detail"]
    listed = client.get("/shop/admin/coupons", headers=auth_headers(admin)).json()
    assert listed[0]["uses"] == 1

    # Cancelling gives the use back.
    client.post(f"/shop/orders/{res.json()['id']}/cancel", json={}, headers=auth_headers(consumer))
    assert client.get("/shop/admin/coupons", headers=auth_headers(admin)).json()[0]["uses"] == 0


def test_free_shipping_above_threshold_and_expired_coupon(client, db, consumer):
    from datetime import timedelta
    from app.core.time import utcnow

    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=500, stock=5)
    _coupon(client, admin, code="OLD", discount_type="flat", discount_value=50, min_order_amount=0,
            starts_at=(utcnow() - timedelta(days=10)).isoformat(), expires_at=(utcnow() - timedelta(days=1)).isoformat())
    q = client.post("/shop/quote", json={"items": [{"product_id": product["id"], "quantity": 1}], "coupon_code": "OLD"}, headers=auth_headers(consumer)).json()
    assert q["coupon_error"] == "This coupon has expired"
    assert q["shipping_fee"] == 0 and q["total_amount"] == 500


def test_customer_cancel_restocks_and_refunds_paid_order(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=5)
    order = _order(client, consumer, [{"product_id": product["id"], "quantity": 3}]).json()
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 2
    assert _pay(client, consumer, order["id"]).json()["status"] == "paid"

    res = client.post(f"/shop/orders/{order['id']}/cancel", json={"reason": "Changed my mind"}, headers=auth_headers(consumer))
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled" and res.json()["refund_status"] == "refunded"
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 5
    # Already cancelled.
    assert client.post(f"/shop/orders/{order['id']}/cancel", json={}, headers=auth_headers(consumer)).status_code == 400


def test_unpaid_order_expires_and_releases_stock(client, db, consumer):
    from datetime import timedelta
    from app.models.shop import ShopOrder

    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=2)
    order = _order(client, consumer, [{"product_id": product["id"], "quantity": 2}]).json()
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 0

    row = db.get(ShopOrder, order["id"])
    row.created_at = row.created_at - timedelta(hours=2)
    db.commit()

    # Paying for it now is refused, and the stock comes back.
    res = client.post(f"/shop/orders/{order['id']}/payment/order", headers=auth_headers(consumer))
    assert res.status_code == 400 and "expired" in res.json()["detail"]
    assert client.get(f"/shop/products/{product['id']}").json()["stock_quantity"] == 2


def test_product_by_slug_and_ad_feed(client, db):
    product = _catalogue_product(db, licence_number="AYUSH/MFG/2026/0001", active=True)
    assert client.get("/shop/products/by-slug/natural-henna-powder").json()["id"] == str(product.id)
    assert client.get("/shop/products/by-slug/nope").status_code == 404

    feed = client.get("/shop/feed.csv")
    assert feed.status_code == 200 and feed.headers["content-type"].startswith("text/csv")
    lines = feed.text.strip().splitlines()
    assert lines[0].startswith("id,item_group_id,title")
    # Two active pack sizes; the retired 1 kg size is left out.
    assert len(lines) == 3
    assert "Natural Henna Powder - 100 g" in lines[1] and "120.00 INR" in lines[1] and "in stock" in lines[1]
    assert "/shop/natural-henna-powder" in lines[1]


def test_coupon_dates_with_timezone_are_stored_as_utc(client, db):
    admin = make_user(db, role="admin")
    c = _coupon(client, admin, code="IST", expires_at="2030-01-01T10:00:00+05:30")
    assert c["expires_at"].startswith("2030-01-01T04:30:00")
    toggled = client.put(f"/shop/admin/coupons/{c['id']}", json={**{k: v for k, v in c.items() if k not in ("id", "uses", "created_at")}, "is_active": False}, headers=auth_headers(admin)).json()
    assert toggled["expires_at"] == c["expires_at"] and toggled["is_active"] is False


def test_admin_retries_a_failed_refund(client, db, consumer, monkeypatch):
    import app.services.shop_orders as shop_orders

    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=5)
    order = _order(client, consumer, [{"product_id": product["id"], "quantity": 1}]).json()
    _pay(client, consumer, order["id"])

    def boom(*args, **kwargs):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(shop_orders, "refund_payment", boom)
    cancelled = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "cancelled"}, headers=auth_headers(admin)).json()
    assert cancelled["status"] == "cancelled" and cancelled["refund_status"] == "failed"
    monkeypatch.undo()

    retried = client.post(f"/admin/shop-orders/{order['id']}/retry-refund", headers=auth_headers(admin))
    assert retried.status_code == 200 and retried.json()["refund_status"] == "refunded"
    assert client.post(f"/admin/shop-orders/{order['id']}/retry-refund", headers=auth_headers(admin)).status_code == 400


def test_paid_orders_get_consecutive_invoice_numbers_and_gst_snapshot(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin, price=100, stock=10)
    edit = client.put(f"/shop/products/{product['id']}", json={"name": product["name"], "price": 100, "hsn_code": "3305", "gst_rate": 18}, headers=auth_headers(admin))
    assert edit.status_code == 200 and edit.json()["gst_rate"] == 18
    assert client.put(f"/shop/products/{product['id']}", json={"name": product["name"], "price": 100, "hsn_code": "33A5"}, headers=auth_headers(admin)).status_code == 422

    def place():
        res = client.post(
            "/shop/orders",
            json={"shipping_name": "Priya", "shipping_phone": "9812345680", "shipping_address": "12 MG Road",
                  "shipping_state": "Delhi", "shipping_pincode": "110001", "items": [{"product_id": product["id"], "quantity": 1}]},
            headers=auth_headers(consumer),
        )
        assert res.status_code == 200, res.text
        return res.json()

    first, second = place(), place()
    assert first["items"][0]["hsn_code"] == "3305" and first["items"][0]["gst_rate"] == 18
    assert first["shipping_state"] == "Delhi" and first["invoice_number"] is None  # numbered only once paid
    a = _pay(client, consumer, second["id"]).json()["invoice_number"]
    b = _pay(client, consumer, first["id"]).json()["invoice_number"]
    assert a.startswith("AV") and len(a) <= 16
    assert int(b.split("-")[1]) == int(a.split("-")[1]) + 1

    bad_pin = client.post(
        "/shop/orders",
        json={"shipping_name": "P", "shipping_phone": "9812345680", "shipping_address": "x", "shipping_pincode": "01234",
              "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=auth_headers(consumer),
    )
    assert bad_pin.status_code == 422
