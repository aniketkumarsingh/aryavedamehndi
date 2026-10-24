import importlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import make_photo, to_bytes

HEURISTIC = json.dumps({"mask": {"backend": "heuristic"}})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("IMAGE_STUDIO_API_KEYS", raising=False)
    from image_studio import server

    return TestClient(importlib.reload(server).app)


def _files(img=None):
    return {"file": ("hand.jpg", to_bytes(img or make_photo()), "image/jpeg")}


def test_health_and_presets(client):
    assert client.get("/health").json()["status"] == "ok"
    presets = client.get("/v1/presets").json()
    assert {"default", "product-white", "studio-warm", "natural-soft"} <= set(presets)


def test_process_returns_image_with_report_headers(client):
    r = client.post("/v1/process?format=webp&width=600&height=600", files=_files(), data={"preset": "product-white", "options": HEURISTIC})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(r.content)).size == (600, 600)
    assert int(r.headers["X-Image-Studio-Score"]) >= 0
    assert "busy_background" in r.headers["X-Image-Studio-Fixed"]


def test_process_json_mode(client):
    r = client.post("/v1/process?response=json&width=300&height=300", files=_files(), data={"preset": "studio-warm", "options": HEURISTIC})
    body = r.json()
    assert body["image"].startswith("data:image/jpeg;base64,")
    assert body["width"] == 300 and "steps" in body["report"]


def test_analyze(client):
    r = client.post("/v1/analyze", files=_files(), data={"preset": "default"})
    assert r.status_code == 200
    assert "score" in r.json() and "issues" in r.json()


@pytest.mark.parametrize(
    "data,query,status",
    [
        ({"preset": "nope"}, "", 400),
        ({"preset": "../../etc/passwd"}, "", 400),
        ({"preset": "default", "options": "{bad json"}, "", 400),
        ({"preset": "default", "options": '{"color": {"bogus": 1}}'}, "", 400),
        ({"preset": "default"}, "?format=gif", 400),
        ({"preset": "default"}, "?width=99999", 400),
    ],
)
def test_bad_requests(client, data, query, status):
    assert client.post(f"/v1/process{query}", files=_files(), data=data).status_code == status


def test_rejects_non_images(client):
    r = client.post("/v1/process", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 415


def test_api_key(monkeypatch):
    monkeypatch.setenv("IMAGE_STUDIO_API_KEYS", "secret1,secret2")
    from image_studio import server

    c = TestClient(importlib.reload(server).app)
    assert c.get("/v1/presets").status_code == 401
    assert c.get("/v1/presets", headers={"X-API-Key": "secret2"}).status_code == 200
    assert c.get("/health").status_code == 200  # health stays open for load balancers
    monkeypatch.delenv("IMAGE_STUDIO_API_KEYS")
    importlib.reload(server)


def test_widget_and_demo_are_served(client):
    assert "customElements.define" in client.get("/widget/image-studio.js").text
    assert "<image-studio" in client.get("/").text
