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
    assert body["total_amount"] == 147
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

    ship_res = client.post(f"/admin/shop-orders/{order['id']}/status", json={"status": "shipped"}, headers=auth_headers(admin))
    assert ship_res.status_code == 200
    assert ship_res.json()["status"] == "shipped"
    assert ship_res.json()["shipped_at"] is not None

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
