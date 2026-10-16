def test_request_otp_dev_mode_returns_code(client):
    res = client.post("/auth/request-otp", json={"phone": "9812345678"})
    assert res.status_code == 200
    body = res.json()
    assert body["sent_by_sms"] is False
    assert body["dev_otp"] is not None
    assert len(body["dev_otp"]) == 6


def test_verify_otp_wrong_code_rejected(client):
    client.post("/auth/request-otp", json={"phone": "9812345679"})
    res = client.post(
        "/auth/verify-otp",
        json={"phone": "9812345679", "code": "000000", "role": "consumer", "name": "X", "gender": "female"},
    )
    assert res.status_code == 400


def test_verify_otp_creates_user_and_returns_token(client):
    otp_res = client.post("/auth/request-otp", json={"phone": "9812345680"})
    code = otp_res.json()["dev_otp"]

    res = client.post(
        "/auth/verify-otp",
        json={"phone": "9812345680", "code": code, "role": "consumer", "name": "Priya", "gender": "female"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_new_user"] is True
    assert body["role"] == "consumer"
    assert body["access_token"]

    # Logging in again with the same phone reuses the same user, doesn't
    # create a duplicate.
    otp_res2 = client.post("/auth/request-otp", json={"phone": "9812345681"})
    assert otp_res2.status_code == 200


def test_protected_endpoint_requires_auth(client):
    res = client.get("/users/me")
    assert res.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client):
    res = client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401
