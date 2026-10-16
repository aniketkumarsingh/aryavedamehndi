from tests.conftest import auth_headers


def test_get_me(client, consumer):
    res = client.get("/users/me", headers=auth_headers(consumer))
    assert res.status_code == 200
    assert res.json()["id"] == str(consumer.id)


def test_update_basic_field_without_consent(client, consumer):
    res = client.put("/users/me", json={"name": "New Name"}, headers=auth_headers(consumer))
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"


def test_sensitive_field_blocked_without_consent(client, consumer):
    res = client.put("/users/me", json={"guardian_name": "Rakesh Verma"}, headers=auth_headers(consumer))
    # Sensitive DPDP-gated fields must be rejected outright before consent,
    # not silently dropped.
    assert res.status_code == 400


def test_sensitive_field_allowed_after_consent(client, consumer):
    consent_res = client.post("/users/me/consent", json={"agree": True}, headers=auth_headers(consumer))
    assert consent_res.status_code == 200
    assert consent_res.json()["consent_given"] is True

    res = client.put("/users/me", json={"guardian_name": "Rakesh Verma"}, headers=auth_headers(consumer))
    assert res.status_code == 200
    assert res.json()["guardian_name"] == "Rakesh Verma"
