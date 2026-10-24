"""HTTP API. Run with `image-studio serve` or `uvicorn image_studio.server:app`.

Environment:
  IMAGE_STUDIO_API_KEYS      comma-separated keys; when set, requests need X-API-Key
  IMAGE_STUDIO_CORS_ORIGINS  comma-separated origins allowed to call the API (default: none)
  IMAGE_STUDIO_MAX_MB        upload limit in MB (default 25)
  IMAGE_STUDIO_CONCURRENCY   images processed at once (default 2)
  IMAGE_STUDIO_PRESETS_DIR   extra preset folder(s), searched before the built-in ones
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from . import __version__
from .config import PresetError, list_presets, load_preset
from .imgio import ImageTooLarge, content_type, normalize_format, open_image
from .mask import ai_available
from .pipeline import analyze, process

WEB_DIR = Path(__file__).parent / "web"
MAX_BYTES = int(float(os.environ.get("IMAGE_STUDIO_MAX_MB", "25")) * 1024 * 1024)
API_KEYS = {k.strip() for k in os.environ.get("IMAGE_STUDIO_API_KEYS", "").split(",") if k.strip()}
ORIGINS = [o.strip() for o in os.environ.get("IMAGE_STUDIO_CORS_ORIGINS", "").split(",") if o.strip()]
_slots = asyncio.Semaphore(int(os.environ.get("IMAGE_STUDIO_CONCURRENCY", "2")))

app = FastAPI(title="Image Studio", version=__version__, description="Analyse, enhance and unify photos.")
if ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
        expose_headers=["X-Image-Studio-Score", "X-Image-Studio-Issues", "X-Image-Studio-Fixed"],
    )


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEYS and x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


async def _read_image(file: UploadFile) -> Image.Image:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"file larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        return open_image(io.BytesIO(data))
    except ImageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=415, detail="not a supported image (jpeg, png, webp, tiff, bmp)")


def _overrides(options: str | None, fmt: str | None, width: int | None, height: int | None) -> dict:
    try:
        out = json.loads(options) if options else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"options is not valid JSON: {exc}")
    if not isinstance(out, dict):
        raise HTTPException(status_code=400, detail="options must be a JSON object")
    output = out.setdefault("output", {})
    if fmt:
        try:
            output["format"] = normalize_format(fmt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    for key, value in (("width", width), ("height", height)):
        if value is not None:
            if not 16 <= value <= 6000:
                raise HTTPException(status_code=400, detail=f"{key} must be between 16 and 6000")
            output[key] = value
    return out


def _config(preset: str, overrides: dict) -> dict:
    if "/" in preset or "\\" in preset or preset.endswith(".json"):
        raise HTTPException(status_code=400, detail="preset must be a preset name")
    try:
        return load_preset(preset, overrides)
    except PresetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "ai_masks": ai_available()}


@app.get("/v1/presets", dependencies=[Depends(require_key)])
def presets() -> dict:
    out = {}
    for name, desc in list_presets().items():
        cfg = load_preset(name)
        o = cfg["output"]
        out[name] = {"description": desc, "background": cfg["background"]["mode"], "width": o["width"], "height": o["height"], "format": o["format"]}
    return out


@app.post("/v1/analyze", dependencies=[Depends(require_key)])
async def analyze_endpoint(file: UploadFile = File(...), preset: str = Form("default")) -> dict:
    img = await _read_image(file)
    _config(preset, {})
    async with _slots:
        return await run_in_threadpool(analyze, img, preset)


@app.post("/v1/process", dependencies=[Depends(require_key)])
async def process_endpoint(
    file: UploadFile = File(...),
    preset: str = Form("default"),
    options: str | None = Form(None, description="JSON object of preset overrides"),
    format: str | None = Query(None, description="jpeg | webp | png"),
    width: int | None = Query(None),
    height: int | None = Query(None),
    response: str = Query("image", pattern="^(image|json)$", description="image bytes, or JSON with a data URL and the report"),
):
    img = await _read_image(file)
    cfg = _config(preset, _overrides(options, format, width, height))
    async with _slots:
        result = await run_in_threadpool(process, img, cfg=cfg)
    data = result.encode()
    fmt = cfg["output"]["format"]
    report = result.report
    if response == "json":
        url = f"data:{content_type(fmt)};base64,{base64.b64encode(data).decode()}"
        return JSONResponse({"image": url, "width": result.image.width, "height": result.image.height, "report": report})
    headers = {
        "X-Image-Studio-Score": str(report["result"]["score"]),
        "X-Image-Studio-Issues": ",".join(report["remaining"]),
        "X-Image-Studio-Fixed": ",".join(report["fixed"]),
        "Cache-Control": "no-store",
    }
    return Response(content=data, media_type=content_type(fmt), headers=headers)


@app.get("/widget/image-studio.js")
def widget() -> FileResponse:
    return FileResponse(WEB_DIR / "image-studio.js", media_type="text/javascript")


@app.get("/")
def demo() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.exception_handler(PresetError)
async def _preset_error(_, exc: PresetError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
