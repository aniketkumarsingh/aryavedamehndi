import io

import numpy as np
import pytest
from PIL import Image

from conftest import HEURISTIC, make_photo, to_bytes
from image_studio import consistency, load_preset, process
from image_studio.compose import subject_region
from image_studio.config import PresetError, deep_merge, parse_set
from image_studio.imgio import encode, open_image


def test_presets_extend_and_validate():
    cfg = load_preset("social-portrait")
    assert cfg["background"]["mode"] == "soften"  # from natural-soft
    assert (cfg["output"]["width"], cfg["output"]["height"]) == (1080, 1350)
    with pytest.raises(PresetError):
        load_preset("default", {"color": {"exposur": 1}})
    with pytest.raises(PresetError):
        load_preset("does-not-exist")
    assert parse_set(["color.exposure=0.5", "background.color=#fff"]) == {"color": {"exposure": 0.5}, "background": {"color": "#fff"}}
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}}) == {"a": {"b": 3, "c": 2}}


def test_replace_background_gives_exact_canvas_and_clean_backdrop(photo):
    res = process(photo, "product-white", HEURISTIC)
    assert res.image.size == (2000, 2000)
    arr = np.asarray(res.image).astype(int)
    for corner in (arr[:40, :40], arr[-40:, -40:], arr[:40, -40:]):
        assert corner.mean() > 245  # white backdrop, stripes gone
    rep = res.report
    assert "busy_background" in {i["code"] for i in rep["source"]["issues"]}
    assert "busy_background" in rep["fixed"]
    assert rep["result"]["background"]["colorfulness"] < rep["source"]["background"]["colorfulness"] / 4
    assert res.image.size == Image.open(io.BytesIO(res.encode())).size


def test_soften_keeps_photo_but_calms_background(photo):
    res = process(photo, "natural-soft", HEURISTIC)
    assert res.image.size == (1600, 1600)
    assert res.report["result"]["background"]["colorfulness"] < res.report["source"]["background"]["colorfulness"] / 2


def test_reference_pulls_colour_cast_back():
    ref = {"L": 75.0, "L_median": 65.0, "L_std": 15.0, "a": 12.0, "b": 14.0, "chroma": 19.0}
    purple = make_photo(cast=(10, -25, 30))
    over = deep_merge(HEURISTIC, {"color": {"reference": ref, "white_balance": 1.0, "max_tint_shift": 25}})
    res = process(purple, "studio-warm", over)
    before, after = res.report["source"]["color"], res.report["result"]["color"]
    dist = lambda c: np.hypot(c["a"] - ref["a"], c["b"] - ref["b"])  # noqa: E731
    assert dist(after) < dist(before) / 2


def test_keep_mode_never_pads_outside_the_photo(photo):
    res = process(photo, "default", deep_merge(HEURISTIC, {"framing": {"mode": "subject", "aspect": "1:1"}, "output": {"max_side": 500}}))
    assert res.image.size == (500, 500)
    x0, y0, x1, y1 = res.report["steps"][1]["region"]
    assert x0 >= 0 and y0 >= 0 and x1 <= 900 and y1 <= 600


def test_subject_leaving_frame_stays_flush():
    mask = np.zeros((100, 100), np.float32)
    mask[0:60, 40:60] = 1  # an arm entering from the top edge
    x0, y0, x1, y1 = subject_region(mask, 1000, 1000, aspect=1.0, margin=0.1, allow_pad=True)
    assert y0 == pytest.approx(0, abs=1)  # top stays on the edge
    assert x1 - x0 == pytest.approx(y1 - y0, rel=1e-3)  # square
    assert y1 > 600  # margin added at the open (bottom) end


def test_no_subject_falls_back_to_center_crop():
    flat = Image.new("RGB", (800, 400), (200, 200, 200))
    res = process(flat, "product-white", {"mask": {"backend": "none"}, "framing": {"mode": "center"}})
    assert res.image.size == (2000, 2000)


def test_blurry_photo_is_not_reported_as_fixed():
    from PIL import ImageFilter

    soft = make_photo().filter(ImageFilter.GaussianBlur(12))
    res = process(soft, "studio-warm", deep_merge(HEURISTIC, {"quality": {"min_sharpness": 50}}))
    assert "blurry" in {i["code"] for i in res.report["source"]["issues"]}
    assert "blurry" in res.report["remaining"]


def test_open_image_applies_exif_and_flattens_alpha():
    img = Image.new("RGBA", (40, 20), (255, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = open_image(io.BytesIO(buf.getvalue()))
    assert out.mode == "RGB" and out.getpixel((0, 0)) == (255, 255, 255)

    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90
    buf = io.BytesIO()
    Image.new("RGB", (40, 20)).save(buf, "JPEG", exif=exif.tobytes())
    assert open_image(io.BytesIO(buf.getvalue())).size == (20, 40)


@pytest.mark.parametrize("fmt", ["jpeg", "webp", "png", "jpg"])
def test_encode_formats_strip_metadata(fmt):
    data = encode(make_photo(120, 80), fmt, 80)
    img = Image.open(io.BytesIO(data))
    assert img.size == (120, 80)
    assert "exif" not in img.info
    assert img.info.get("icc_profile")


def test_renditions_and_consistency(photo):
    over = deep_merge(HEURISTIC, {"output": {"renditions": [{"suffix": "-400", "width": 400, "format": "webp"}]}})
    res = process(to_bytes(photo), "studio-warm", over)
    (r,) = res.renditions()
    assert r["suffix"] == "-400" and Image.open(io.BytesIO(r["data"])).size == (400, 400)
    spread = consistency([res.report["source"], res.report["result"]])
    assert set(spread) >= {"subject_L", "subject_a", "subject_b", "background_colorfulness"}
