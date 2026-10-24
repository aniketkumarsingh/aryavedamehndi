"""Presets: JSON files that describe a look. Every preset is merged over DEFAULTS,
and a preset may name another one in "extends" to inherit from it."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

PRESET_DIR = Path(__file__).parent / "presets"

DEFAULTS: dict = {
    "name": "default",
    "description": "",
    "extends": None,
    "output": {
        # Exact canvas when width and height are both set; otherwise fit inside max_side.
        "width": None,
        "height": None,
        "max_side": 2048,
        "format": "jpeg",  # jpeg | webp | png
        "quality": 88,
        "upscale": True,  # allow enlarging small sources (only applies to max_side)
        "renditions": [],  # [{"suffix": "-800", "width": 800, "format": "webp", "quality": 82}]
    },
    "mask": {
        "backend": "auto",  # auto (AI if installed, else heuristic) | ai | heuristic | none
        # birefnet-general: best edges and fewest props left in (~15 s/photo on CPU).
        # isnet-general-use: ~1.5 s/photo, but loses forearms/feet more often.
        "model": "birefnet-general",
        "min_component": 0.01,  # drop subject fragments smaller than this share of the frame
    },
    "framing": {
        "mode": "subject",  # subject | center | none
        "aspect": None,  # "1:1", "4:5", ... (width/height in output win)
        "margin": 0.06,  # space around the subject, as a share of its longest side
    },
    "background": {
        "mode": "keep",  # keep | soften | replace
        "color": "#FFFFFF",
        "color2": None,  # edge colour for a soft radial gradient
        "soften": {"blur": 0.015, "desaturate": 0.8, "tint": 0.55},
        "shadow": 0.0,  # contact shadow strength (replace mode)
        "edge_feather": 1.2,  # px
    },
    "color": {
        # Subject statistics to match (written by `image-studio calibrate`).
        # Without one, white balance uses neutral pixels and exposure aims at target_L.
        "reference": None,
        "target_L": 72.0,
        "white_balance": 0.7,
        "exposure": 0.8,
        "contrast": 0.0,
        "saturation": 0.5,
        "vibrance": 0.0,
        "local_contrast": 0.3,
        "max_tint_shift": 10.0,
    },
    "detail": {
        "denoise": "auto",  # auto | off | on
        "sharpen": "auto",  # auto | off | <amount>
    },
    "watermark": {
        "text": None,
        "opacity": 0.35,
        "position": "bottom-right",
        "scale": 0.028,
        "color": "#FFFFFF",
    },
    "quality": {
        "min_long_side": 1600,
        "min_sharpness": 45.0,  # edge sharpness; flags clear blur only - confirm by eye
        "min_fill": 0.12,
        "max_background_busy": 0.08,
        "max_background_colorfulness": 40.0,
    },
}

# Keys whose value is free-form (not checked against DEFAULTS).
_FREE_FORM = {("color", "reference"), ("output", "renditions")}


class PresetError(ValueError):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def validate(override: dict, defaults: dict = DEFAULTS, path: tuple = ()) -> None:
    for key, value in override.items():
        here = path + (key,)
        if key.startswith("_"):  # "_comment"-style keys are notes, ignored
            continue
        if key not in defaults:
            raise PresetError(f"unknown setting '{'.'.join(here)}'")
        if here in _FREE_FORM:
            continue
        if isinstance(defaults[key], dict):
            if not isinstance(value, dict):
                raise PresetError(f"'{'.'.join(here)}' must be an object")
            validate(value, defaults[key], here)


def _search_dirs() -> list[Path]:
    dirs = [PRESET_DIR]
    extra = os.environ.get("IMAGE_STUDIO_PRESETS_DIR")
    if extra:
        dirs = [Path(p) for p in extra.split(os.pathsep) if p] + dirs
    return dirs


def _find(name: str) -> Path:
    candidate = Path(name)
    if candidate.suffix == ".json" and candidate.exists():
        return candidate
    for d in _search_dirs():
        p = d / f"{name}.json"
        if p.exists():
            return p
    raise PresetError(f"preset '{name}' not found")


def _load_raw(name: str, seen: tuple = ()) -> dict:
    path = _find(name)
    if str(path) in seen:
        raise PresetError(f"preset '{name}' extends itself")
    data = json.loads(path.read_text())
    validate(data)
    parent = data.get("extends")
    if parent:
        return deep_merge(_load_raw(parent, seen + (str(path),)), data)
    return data


def load_preset(name: str | None = "default", overrides: dict | None = None) -> dict:
    cfg = deep_merge(DEFAULTS, _load_raw(name or "default"))
    if overrides:
        validate(overrides)
        cfg = deep_merge(cfg, overrides)
    return cfg


def list_presets() -> dict[str, str]:
    found: dict[str, str] = {}
    for d in reversed(_search_dirs()):
        for p in sorted(d.glob("*.json")):
            try:
                found[p.stem] = json.loads(p.read_text()).get("description", "")
            except (OSError, json.JSONDecodeError):
                continue
    return found


def parse_set(items: list[str]) -> dict:
    """['color.exposure=0.5', 'background.mode=replace'] -> nested dict."""
    out: dict = {}
    for item in items:
        if "=" not in item:
            raise PresetError(f"expected key=value, got '{item}'")
        key, raw = item.split("=", 1)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def output_aspect(cfg: dict) -> float | None:
    out = cfg["output"]
    if out["width"] and out["height"]:
        return out["width"] / out["height"]
    aspect = cfg["framing"]["aspect"]
    if aspect:
        w, h = (float(x) for x in str(aspect).split(":"))
        return w / h
    return None


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise PresetError(f"bad colour '{value}'")
    return tuple(int(v[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
