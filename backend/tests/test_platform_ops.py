import os
import shutil
import subprocess
import time
from datetime import timedelta

import pytest

from app.core import observability
from app.core.time import utcnow
from app.models.job import Job
from app.services import backups, health
from app.services.otp import _generate_code
from tests.conftest import auth_headers, make_user
from tests.test_shop import _make_product


# ---------------------------------------------------------------- limits --

def test_otp_requests_are_limited_per_ip_across_phone_numbers(client):
    # Different numbers each time: the per-phone limit never triggers, so
    # this is the per-IP guard against SMS pumping.
    for i in range(10):
        assert client.post("/auth/request-otp", json={"phone": f"98{i:08d}"}).status_code == 200
    blocked = client.post("/auth/request-otp", json={"phone": "9811111111"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_otp_verify_is_limited_per_phone(client):
    client.post("/auth/request-otp", json={"phone": "9876500000"})
    codes = [client.post("/auth/verify-otp", json={"phone": "9876500000", "code": "000000"}).status_code for _ in range(11)]
    assert codes[:10] == [400] * 10 and codes[10] == 429


def test_coupon_guessing_is_limited(client, db, consumer):
    admin = make_user(db, role="admin")
    product = _make_product(client, admin)
    body = {"items": [{"product_id": product["id"], "quantity": 1}]}
    statuses = [client.post("/shop/quote", json={**body, "coupon_code": f"GUESS{i}"}, headers=auth_headers(consumer)).status_code for i in range(31)]
    assert statuses[:30] == [200] * 30 and statuses[30] == 429
    # Quotes without a coupon aren't counted.
    assert client.post("/shop/quote", json=body, headers=auth_headers(consumer)).status_code == 200


def test_otp_codes_are_six_random_digits():
    codes = {_generate_code() for _ in range(200)}
    assert all(len(c) == 6 and c.isdigit() for c in codes) and len(codes) > 150


# ---------------------------------------------------------------- health --

def test_liveness_and_readiness(client, db, monkeypatch):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["database"] == "ok"

    db.add(Job(kind="jobs.cleanup", status="queued", run_at=utcnow() - timedelta(minutes=30), created_at=utcnow()))
    db.commit()
    lagging = client.get("/health/ready")
    assert lagging.status_code == 503 and "worker" in lagging.json()["problems"][0]


def test_readiness_in_production_wants_a_live_worker_and_recent_backup(client, monkeypatch):
    monkeypatch.setattr(health.settings, "app_env", "production")
    problems = client.get("/health/ready").json()["problems"]
    assert any("worker" in p for p in problems) and any("backup" in p for p in problems)


# --------------------------------------------------------------- backups --

def test_backup_writes_a_verified_dump_and_prunes_old_ones(tmp_path, monkeypatch):
    if not shutil.which("pg_dump"):
        pytest.skip("pg_dump not installed")
    monkeypatch.setattr(backups.settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(backups.settings, "backup_s3_bucket", "")
    monkeypatch.setattr(backups.settings, "s3_bucket", "")
    old = tmp_path / "aryaveda-20200101-000000.dump"
    old.write_bytes(b"old")
    stale = time.time() - 40 * 86400
    os.utime(old, (stale, stale))
    try:
        result = backups.run_backup()
    except subprocess.CalledProcessError as exc:
        if b"version mismatch" in (exc.stderr or b""):
            pytest.skip("pg_dump is older than the server")
        raise
    assert result["bytes"] > 0 and result["removed"] == 1
    dumps = list(tmp_path.glob("aryaveda-*.dump"))
    assert len(dumps) == 1 and dumps[0].read_bytes().startswith(b"PGDMP")


# -------------------------------------------------------------- sentry --

def test_error_tracking_is_off_without_a_dsn(monkeypatch):
    monkeypatch.setattr(observability.settings, "sentry_dsn", "")
    assert observability.init_sentry("test") is False
    observability.capture(RuntimeError("ignored"))  # no-op, no crash
