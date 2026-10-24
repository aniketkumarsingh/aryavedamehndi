from io import BytesIO

from PIL import Image

from tests.conftest import auth_headers, make_package, make_user


def _png(color) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


def _setup(client, db):
    admin = make_user(db, role="admin")
    package = make_package(db)
    design = client.post(
        "/designs",
        json={"package_id": str(package.id), "name": "Arabic Bel", "price_min": 500, "price_max": 900},
        headers=auth_headers(admin),
    ).json()
    main = client.post(f"/designs/{design['id']}/image", files={"file": ("m.png", _png((200, 0, 0)), "image/png")}, headers=auth_headers(admin)).json()
    return admin, main


def _add(client, admin, design_id, color, label=None, kind="detail"):
    data = {"kind": kind, **({"label": label} if label else {})}
    res = client.post(f"/designs/{design_id}/gallery", data=data, files={"file": ("g.png", _png(color), "image/png")}, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    return res.json()


def test_gallery_views_show_on_design_page_in_order(client, db):
    admin, design = _setup(client, db)
    a = _add(client, admin, design["id"], (0, 200, 0), "Palm close-up")
    b = _add(client, admin, design["id"], (0, 0, 200), "Side view", kind="angle")

    detail = client.get(f"/designs/{design['id']}").json()
    assert [(i["label"], i["kind"]) for i in detail["images"]] == [("Palm close-up", "detail"), ("Side view", "angle")]
    assert detail["image_count"] == 3
    assert client.get("/designs").json()[0]["image_count"] == 3
    assert [i["id"] for i in client.get(f"/designs/{design['id']}/gallery", headers=auth_headers(admin)).json()] == [a["id"], b["id"]]


def test_gallery_is_admin_only_and_validates_kind(client, db):
    admin, design = _setup(client, db)
    consumer = make_user(db)
    res = client.post(f"/designs/{design['id']}/gallery", data={"kind": "detail"}, files={"file": ("g.png", _png((1, 2, 3)), "image/png")}, headers=auth_headers(consumer))
    assert res.status_code == 403
    bad = client.post(f"/designs/{design['id']}/gallery", data={"kind": "selfie"}, files={"file": ("g.png", _png((1, 2, 3)), "image/png")}, headers=auth_headers(admin))
    assert bad.status_code == 422


def test_make_main_swaps_with_current_main_photo(client, db):
    admin, design = _setup(client, db)
    view = _add(client, admin, design["id"], (0, 200, 0), "Better angle", kind="angle")

    res = client.post(f"/designs/{design['id']}/gallery/{view['id']}/make-main", headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["image_url"] == view["url"]
    gallery = client.get(f"/designs/{design['id']}").json()["images"]
    assert [(g["url"], g["label"]) for g in gallery] == [(design["image_url"], "Previous main photo")]


def test_remove_gallery_image(client, db):
    admin, design = _setup(client, db)
    view = _add(client, admin, design["id"], (0, 200, 0))
    assert client.delete(f"/designs/{design['id']}/gallery/{view['id']}", headers=auth_headers(admin)).status_code == 204
    assert client.get(f"/designs/{design['id']}").json()["images"] == []
    assert client.delete(f"/designs/{design['id']}/gallery/{view['id']}", headers=auth_headers(admin)).status_code == 404


def _big_png(color, size=2400) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


def test_large_uploads_get_a_light_display_copy_and_a_full_res_zoom_copy(client, db):
    admin, design = _setup(client, db)
    res = client.post(f"/designs/{design['id']}/image", files={"file": ("big.png", _big_png((150, 60, 20)), "image/png")}, headers=auth_headers(admin)).json()
    assert res["image_hd_url"] and res["image_hd_url"] != res["image_url"]
    display = Image.open(BytesIO(client.get(res["image_url"]).content))
    full = Image.open(BytesIO(client.get(res["image_hd_url"]).content))
    assert max(display.size) == 1600 and display.format == "JPEG"
    assert full.size == (2400, 2400)

    view = client.post(f"/designs/{design['id']}/gallery", data={"kind": "angle"}, files={"file": ("a.png", _big_png((10, 10, 10)), "image/png")}, headers=auth_headers(admin)).json()
    assert view["hd_url"]
    # Small uploads are served as-is - no pointless second copy.
    small = _add(client, admin, design["id"], (5, 5, 5))
    assert small["hd_url"] is None

    # Make-main carries the zoom copy across in both directions.
    swapped = client.post(f"/designs/{design['id']}/gallery/{view['id']}/make-main", headers=auth_headers(admin)).json()
    assert (swapped["image_url"], swapped["image_hd_url"]) == (view["url"], view["hd_url"])
    prev = [i for i in client.get(f"/designs/{design['id']}").json()["images"] if i["label"] == "Previous main photo"][0]
    assert (prev["url"], prev["hd_url"]) == (res["image_url"], res["image_hd_url"])


def test_spin_frames_are_ordered_by_file_name_and_kept_out_of_the_gallery(client, db):
    admin, design = _setup(client, db)
    files = [("files", (f"{n:02d}.png", _png((n * 20, 0, 0)), "image/png")) for n in (3, 1, 2, 5, 4, 8, 6, 7, 10, 9)]
    res = client.put(f"/designs/{design['id']}/spin", files=files, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    assert [f["label"] for f in res.json()][:3] == ["Frame 1", "Frame 2", "Frame 3"]

    detail = client.get(f"/designs/{design['id']}").json()
    assert detail["spin_frame_count"] == 10 and len(detail["spin_frames"]) == 10
    assert detail["images"] == [] and detail["image_count"] == 1
    assert client.get(f"/designs/{design['id']}/gallery", headers=auth_headers(admin)).json() == []
    # Frame order follows file names, not upload order: 01 is red=20.
    first = Image.open(BytesIO(client.get(detail["spin_frames"][0]["url"]).content)).convert("RGB").getpixel((0, 0))
    assert first == (20, 0, 0)

    # Uploading again replaces the set; too few frames is refused.
    assert client.put(f"/designs/{design['id']}/spin", files=files[:8], headers=auth_headers(admin)).status_code == 200
    assert client.get(f"/designs/{design['id']}").json()["spin_frame_count"] == 8
    assert client.put(f"/designs/{design['id']}/spin", files=files[:3], headers=auth_headers(admin)).status_code == 400
    assert client.put(f"/designs/{design['id']}/spin", files=files, headers=auth_headers(make_user(db))).status_code == 403
    assert client.delete(f"/designs/{design['id']}/spin", headers=auth_headers(admin)).status_code == 204
    assert client.get(f"/designs/{design['id']}").json()["spin_frame_count"] == 0


def test_save_image_variants_can_use_a_fixed_name(tmp_path, monkeypatch):
    import pytest

    from app.services import storage

    monkeypatch.setattr(storage, "MEDIA_DIR", tmp_path)
    buf = BytesIO()
    Image.new("RGB", (2400, 1600), (150, 70, 30)).save(buf, format="JPEG")
    url, hd_url = storage.save_image_variants(buf.getvalue(), "catalog", name="bridal-01-4821")
    assert (url, hd_url) == ("/media/catalog/bridal-01-4821.jpg", "/media/catalog/bridal-01-4821-hd.jpg")
    assert (tmp_path / "catalog/bridal-01-4821-hd.jpg").read_bytes() == buf.getvalue()
    with pytest.raises(ValueError):
        storage.save_upload(buf.getvalue(), "catalog", name="../kyc/x")
