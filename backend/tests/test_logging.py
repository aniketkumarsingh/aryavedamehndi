import json
import logging

from app import main
from app.core.logging import ContextFilter, JsonFormatter, order_id_var, request_id_var
from tests.conftest import auth_headers


def test_request_id_is_returned_and_kept_from_the_proxy(client):
    res = client.get("/health")
    assert len(res.headers["x-request-id"]) == 16
    assert client.get("/health", headers={"X-Request-ID": "caddy-abc12345"}).headers["x-request-id"] == "caddy-abc12345"
    assert client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"}).headers["x-request-id"] != "bad id\nwith newline"


def test_access_line_carries_user_and_order(client, consumer, caplog, monkeypatch):
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/shop/orders/3f2c1e4b-0000-4000-8000-000000000001", headers=auth_headers(consumer))
    line = next(r for r in caplog.records if r.name == "app.access")
    assert line.status == 404 and line.user_id == str(consumer.id)
    assert line.path.endswith("000000000001") and line.duration_ms >= 0

    monkeypatch.setattr(main.settings, "slow_request_ms", -1)
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/health")
    assert any(r.getMessage() == "slow request" and r.levelno == logging.WARNING for r in caplog.records)


def test_json_lines_include_context():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "refund queued for %s", ("₹100",), None)
    tokens = request_id_var.set("req-123456"), order_id_var.set("ord-1")
    try:
        ContextFilter().filter(record)
    finally:
        request_id_var.reset(tokens[0])
        order_id_var.reset(tokens[1])
    line = json.loads(JsonFormatter("api").format(record))
    assert line["msg"] == "refund queued for ₹100" and line["request_id"] == "req-123456" and line["order_id"] == "ord-1"
    assert line["service"] == "api" and line["level"] == "info"
