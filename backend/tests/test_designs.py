from io import BytesIO

from PIL import Image

from tests.conftest import auth_headers, make_approved_artist, make_package, make_user

LAT, LNG = 28.6139, 77.2090  # same as make_approved_artist's default base


def _png(color=(120, 40, 30), pattern=False) -> bytes:
    img = Image.new("RGB", (64, 64), color)
    if pattern:
        for x in range(0, 64, 8):
            for y in range(0, 64, 8):
                if (x + y) % 16 == 0:
                    img.paste((250, 240, 220), (x, y, x + 8, y + 8))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_design(client, admin, package, **overrides):
    body = {
        "package_id": str(package.id),
        "name": "Peacock Bridal Full Hand",
        "description": "Peacock motif, front and back",
        "price_min": 5000,
        "price_max": 8000,
        "duration_minutes": 180,
        **overrides,
    }
    res = client.post("/designs", json=body, headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    return res.json()


def _offer(client, artist_user, design_id, image=None):
    res = client.post(
        f"/artists/me/designs/{design_id}",
        files={"file": ("proof.png", image or _png(), "image/png")},
        headers=auth_headers(artist_user),
    )
    assert res.status_code == 200, res.text
    return res.json()


def _approve(client, admin, offer_id):
    res = client.post(f"/admin/design-photos/{offer_id}/approve", headers=auth_headers(admin))
    assert res.status_code == 200, res.text
    return res.json()


def _setup(client, db, **design_overrides):
    """Admin, bridal package (band 4000-15000), a design priced inside it,
    and an approved artist who offers the design with an approved photo."""
    admin = make_user(db, role="admin")
    package = make_package(db, package_type="bridal", price_min=4000, price_max=15000)
    design = _create_design(client, admin, package, **design_overrides)
    artist_user, profile = make_approved_artist(db)
    offer = _offer(client, artist_user, design["id"])
    _approve(client, admin, offer["id"])
    return admin, package, design, artist_user, profile


def _book(client, consumer, artist_user, package, design_id=None, **extra):
    body = {
        "artist_id": str(artist_user.id),
        "package_id": str(package.id),
        "location_lat": LAT,
        "location_lng": LNG,
        "scheduled_at": "2026-11-20T10:00:00",
        **({"design_id": design_id} if design_id else {}),
        **extra,
    }
    return client.post("/bookings", json=body, headers=auth_headers(consumer))


# ---------------------------------------------------------------- catalog --

def test_admin_manages_catalog_and_public_lists_by_category(client, db):
    admin = make_user(db, role="admin")
    bridal = make_package(db, package_type="bridal")
    feet = make_package(db, package_type="feet")
    d1 = _create_design(client, admin, bridal)
    _create_design(client, admin, feet, name="Simple Feet Jaal", price_min=400, price_max=700)

    assert client.post("/designs", json={"package_id": str(bridal.id), "name": "x", "price_min": 1, "price_max": 2}, headers=auth_headers(make_user(db))).status_code == 403
    bad = client.post("/designs", json={"package_id": str(bridal.id), "name": "x", "price_min": 900, "price_max": 100}, headers=auth_headers(admin))
    assert bad.status_code == 422

    img = client.post(f"/designs/{d1['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    assert img.json()["image_url"].startswith("/media/catalog/")

    bridal_only = client.get("/designs", params={"category": "bridal"}).json()
    assert [d["name"] for d in bridal_only] == ["Peacock Bridal Full Hand"]
    assert bridal_only[0]["category"] == "bridal"
    assert bridal_only[0]["price_min"] == 5000 and bridal_only[0]["artist_count"] == 0
    assert len(client.get("/designs").json()) == 2


def test_deactivated_design_is_hidden_publicly_but_kept_for_admin(client, db):
    admin = make_user(db, role="admin")
    design = _create_design(client, admin, make_package(db))
    assert client.delete(f"/designs/{design['id']}", headers=auth_headers(admin)).status_code == 204
    assert client.get("/designs").json() == []
    assert client.get(f"/designs/{design['id']}").status_code == 404
    all_designs = client.get("/designs/admin/all", headers=auth_headers(admin)).json()
    assert [d["is_active"] for d in all_designs] == [False]
    assert client.get("/designs/admin/all", headers=auth_headers(make_user(db))).status_code == 403


# ------------------------------------------------------ artist photo review --

def test_artist_photo_is_hidden_until_admin_approves(client, db):
    admin = make_user(db, role="admin")
    design = _create_design(client, admin, make_package(db, price_min=4000, price_max=15000))
    artist_user, _ = make_approved_artist(db)

    offer = _offer(client, artist_user, design["id"])
    assert offer["status"] == "pending"
    assert client.get(f"/designs/{design['id']}").json()["artists"] == []
    assert client.get(f"/artists/{artist_user.id}/designs").json() == []

    queue = client.get("/admin/design-photos", headers=auth_headers(admin)).json()
    assert [q["id"] for q in queue] == [offer["id"]]
    assert queue[0]["artist_phone"] == artist_user.phone

    _approve(client, admin, offer["id"])
    detail = client.get(f"/designs/{design['id']}").json()
    assert [a["artist_id"] for a in detail["artists"]] == [str(artist_user.id)]
    assert detail["artists"][0]["proof_image_url"] == offer["proof_image_url"]
    assert detail["artist_count"] == 1
    assert client.get("/designs").json()[0]["artist_count"] == 1
    assert [d["design"]["id"] for d in client.get(f"/artists/{artist_user.id}/designs").json()] == [design["id"]]
    assert client.get("/admin/design-photos", headers=auth_headers(admin)).json() == []


def test_rejected_photo_shows_reason_and_reupload_goes_back_to_review(client, db):
    admin = make_user(db, role="admin")
    design = _create_design(client, admin, make_package(db))
    artist_user, _ = make_approved_artist(db)
    offer = _offer(client, artist_user, design["id"])

    assert client.post(f"/admin/design-photos/{offer['id']}/reject", json={"reason": "x"}, headers=auth_headers(admin)).status_code == 422
    client.post(f"/admin/design-photos/{offer['id']}/reject", json={"reason": "Photo is blurry"}, headers=auth_headers(admin))
    mine = client.get("/artists/me/designs", headers=auth_headers(artist_user)).json()
    assert (mine[0]["status"], mine[0]["rejection_reason"]) == ("rejected", "Photo is blurry")
    notes = client.get("/notifications", headers=auth_headers(artist_user)).json()
    notes = notes["items"] if isinstance(notes, dict) else notes
    assert any("blurry" in (n["body"] or "") for n in notes)

    again = _offer(client, artist_user, design["id"], image=_png((10, 90, 10)))
    assert (again["id"], again["status"], again["rejection_reason"]) == (offer["id"], "pending", None)
    assert len(client.get("/artists/me/designs", headers=auth_headers(artist_user)).json()) == 1


def test_unapproved_kyc_artist_is_not_listed_even_with_approved_photo(client, db):
    admin, _, design, artist_user, profile = _setup(client, db)
    profile.kyc_status = "pending"
    db.commit()
    assert client.get(f"/designs/{design['id']}").json()["artists"] == []


def test_design_page_filters_artists_by_service_area(client, db):
    _, _, design, artist_user, profile = _setup(client, db)
    near = client.get(f"/designs/{design['id']}", params={"lat": LAT + 0.01, "lng": LNG}).json()["artists"]
    assert near[0]["distance_km"] == 1.1 and near[0]["eta_minutes"] >= 5
    far = client.get(f"/designs/{design['id']}", params={"lat": LAT + 1, "lng": LNG}).json()["artists"]
    assert far == []  # ~111 km, outside the default 10 km service radius


def test_nearby_search_includes_each_artists_approved_designs(client, db):
    admin, package, design, artist_user, _ = _setup(client, db)
    second = _create_design(client, admin, package, name="Arabic Bel", price_min=4500, price_max=6000)
    _offer(client, artist_user, second["id"])  # still pending - must not show

    results = client.get("/artists/nearby", params={"lat": LAT, "lng": LNG}).json()
    mine = next(r for r in results if r["user_id"] == str(artist_user.id))
    assert [(d["name"], d["category"], d["price_min"]) for d in mine["designs"]] == [("Peacock Bridal Full Hand", "bridal", 5000)]


def test_artist_can_stop_offering(client, db):
    _, _, design, artist_user, _ = _setup(client, db)
    assert client.delete(f"/artists/me/designs/{design['id']}", headers=auth_headers(artist_user)).status_code == 204
    assert client.get(f"/designs/{design['id']}").json()["artists"] == []
    assert client.delete(f"/artists/me/designs/{design['id']}", headers=auth_headers(artist_user)).status_code == 404


# ---------------------------------------------------------- booking a design --

def test_booking_a_design_uses_its_price_range_duration_and_image(client, db, consumer):
    admin, package, design, artist_user, _ = _setup(client, db)
    client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    design = client.get(f"/designs/{design['id']}").json()

    res = _book(client, consumer, artist_user, package, design["id"])
    assert res.status_code == 200, res.text
    booking = res.json()
    assert booking["design_id"] == design["id"]
    assert booking["design_name"] == "Peacock Bridal Full Hand"
    assert booking["reference_design_image_url"] == design["image_url"]
    assert (booking["package_price_min"], booking["package_price_max"]) == (5000, 8000)
    assert booking["package_duration_minutes"] == 180

    # 4500 is inside the package band (4000-15000) but outside the design's.
    c, a = auth_headers(consumer), auth_headers(artist_user)
    assert client.post(f"/bookings/{booking['id']}/offers", json={"amount": 4500}, headers=c).status_code == 400
    assert client.post(f"/bookings/{booking['id']}/accept", json={"amount": 9000}, headers=a).status_code == 400
    assert client.post(f"/bookings/{booking['id']}/accept", json={"amount": 6000}, headers=a).status_code == 200


def test_illustrated_design_is_not_used_as_the_verification_reference(client, db, consumer):
    from app.models.catalog import Design

    admin, package, design, artist_user, _ = _setup(client, db)
    client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    row = db.get(Design, design["id"])
    row.image_kind, row.image_credit = "illustration", {"generator": "test"}
    db.commit()

    shown = client.get(f"/designs/{design['id']}").json()
    assert (shown["image_kind"], shown["image_credit"]) == ("illustration", {"generator": "test"})
    booking = _book(client, consumer, artist_user, package, design["id"]).json()
    assert booking["reference_design_image_url"] is None  # consumer confirms instead

    # A real photo uploaded by the admin makes it a photo again.
    client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    assert client.get(f"/designs/{design['id']}").json()["image_kind"] == "photo"


def test_opening_offer_is_checked_against_design_range(client, db, consumer):
    _, package, design, artist_user, _ = _setup(client, db)
    assert _book(client, consumer, artist_user, package, design["id"], opening_offer=4500).status_code == 400
    assert _book(client, consumer, artist_user, package, design["id"], opening_offer=5500).status_code == 200


def test_cannot_book_a_design_the_artist_does_not_offer(client, db, consumer):
    admin, package, design, _, _ = _setup(client, db)
    other_artist, _ = make_approved_artist(db)
    res = _book(client, consumer, other_artist, package, design["id"])
    assert res.status_code == 400 and "doesn't offer" in res.json()["detail"]

    pending_artist, _ = make_approved_artist(db)
    _offer(client, pending_artist, design["id"])
    assert _book(client, consumer, pending_artist, package, design["id"]).status_code == 400


def test_design_must_belong_to_the_booked_package(client, db, consumer):
    _, _, design, artist_user, _ = _setup(client, db)
    other_package = make_package(db, package_type="party")
    res = _book(client, consumer, artist_user, other_package, design["id"])
    assert res.status_code == 400 and "different package" in res.json()["detail"]


def test_finished_photo_is_scored_against_the_design_image(client, db, consumer):
    admin, package, design, artist_user, _ = _setup(client, db)
    art = _png(pattern=True)
    client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", art, "image/png")}, headers=auth_headers(admin))
    booking_id = _book(client, consumer, artist_user, package, design["id"]).json()["id"]

    a = auth_headers(artist_user)
    client.post(f"/bookings/{booking_id}/accept", json={"amount": 6000}, headers=a)
    client.post(f"/bookings/{booking_id}/enroute", headers=a)
    client.post(f"/bookings/{booking_id}/arrived", params={"lat": LAT, "lng": LNG}, headers=a)
    client.post(f"/bookings/{booking_id}/start", headers=a)
    upload = client.post(f"/bookings/{booking_id}/design-upload", files={"file": ("done.png", art, "image/png")}, headers=a)
    assert upload.status_code == 200
    assert upload.json()["similarity_score"] == 100.0
    assert upload.json()["match_status"] == "auto_matched"


def test_plain_package_booking_still_works_without_a_design(client, db, consumer):
    _, package, _, artist_user, _ = _setup(client, db)
    res = _book(client, consumer, artist_user, package)
    assert res.status_code == 200
    assert res.json()["design_id"] is None
    assert (res.json()["package_price_min"], res.json()["package_price_max"]) == (4000, 15000)


def test_artist_photo_can_become_the_catalog_photo_only_with_consent(client, db):
    admin, package, design, artist_user, _ = _setup(client, db)  # approved, no consent
    client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    old_main = client.get(f"/designs/{design['id']}").json()["image_url"]
    offer = client.get("/artists/me/designs", headers=auth_headers(artist_user)).json()[0]
    assert offer["catalog_consent"] is False
    assert client.post(f"/admin/design-photos/{offer['id']}/use-as-catalog", headers=auth_headers(admin)).status_code == 400

    # Re-upload with consent -> pending again -> can't use until approved.
    res = client.post(f"/artists/me/designs/{design['id']}", data={"catalog_consent": "true"}, files={"file": ("p.png", _png((9, 9, 9)), "image/png")}, headers=auth_headers(artist_user))
    offer = res.json()
    assert offer["catalog_consent"] is True and offer["status"] == "pending"
    assert client.post(f"/admin/design-photos/{offer['id']}/use-as-catalog", headers=auth_headers(admin)).status_code == 400
    _approve(client, admin, offer["id"])

    used = client.post(f"/admin/design-photos/{offer['id']}/use-as-catalog", headers=auth_headers(admin))
    assert used.status_code == 200 and used.json()["image_url"] == offer["proof_image_url"]
    gallery = client.get(f"/designs/{design['id']}").json()["images"]
    assert [(g["url"], g["label"]) for g in gallery] == [(old_main, "Previous catalog photo")]
    assert client.post(f"/admin/design-photos/{offer['id']}/use-as-catalog", headers=auth_headers(admin)).status_code == 400
    notes = client.get("/notifications", headers=auth_headers(artist_user)).json()
    notes = notes["items"] if isinstance(notes, dict) else notes
    assert any("catalog photo" in n["title"] for n in notes)


def test_designs_filter_by_style_coverage_and_occasion(client, db):
    admin = make_user(db, role="admin")
    package = make_package(db, package_type="party", price_min=500, price_max=3000)
    a = _create_design(client, admin, package, name="Arabic Bel", style="arabic", coverage="back", occasions=["eid", "party"])
    b = _create_design(client, admin, package, name="Palm Mandala", style="mandala", coverage="palm", occasions=["diwali"])
    assert (a["style"], a["coverage"], a["occasions"]) == ("arabic", "back", ["eid", "party"])

    def names(**query):
        return sorted(d["name"] for d in client.get("/designs", params=query).json())

    assert names() == ["Arabic Bel", "Palm Mandala"]
    assert names(style="arabic") == ["Arabic Bel"]
    assert names(coverage="palm", occasion="diwali") == ["Palm Mandala"]
    assert names(occasion="teej") == []
    assert client.get("/designs", params={"style": "glitter"}).status_code == 422
    body = {"package_id": str(package.id), "name": "X", "price_min": 500, "price_max": 900, "occasions": ["halloween"]}
    bad = client.post("/designs", json=body, headers=auth_headers(admin))
    assert bad.status_code == 422
    assert b["id"]


def test_hidden_design_waiting_for_a_photo_is_published_with_one(client, db):
    admin = make_user(db, role="admin")
    package = make_package(db, package_type="groom", price_min=300, price_max=2500)
    design = _create_design(client, admin, package, name="Sehra Motif", style="indian", is_active=False, photo_needed="A man's palm with a sehra motif")
    assert client.get(f"/designs/{design['id']}").status_code == 404
    listed = {d["name"]: d for d in client.get("/designs/admin/all", headers=auth_headers(admin)).json()}
    assert listed["Sehra Motif"]["photo_needed"] == "A man's palm with a sehra motif"

    up = client.post(f"/designs/{design['id']}/image", files={"file": ("d.png", _png(), "image/png")}, headers=auth_headers(admin))
    assert up.status_code == 200 and up.json()["photo_needed"] is None and up.json()["is_active"] is False
    shown = client.put(f"/designs/{design['id']}", json={**up.json(), "is_active": True}, headers=auth_headers(admin))
    assert shown.status_code == 200 and shown.json()["style"] == "indian"
    assert client.get(f"/designs/{design['id']}").status_code == 200
