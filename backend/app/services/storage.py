"""Stores uploaded images (portfolios, KYC docs, reference designs,
completed-work photos, CMS media).

Uses S3-compatible object storage when configured; otherwise falls back to
local disk under ./media, served by FastAPI's static file mount, so the
whole app runs with zero external accounts during local development.
"""

import uuid
from io import BytesIO
from pathlib import Path

import boto3
from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

settings = get_settings()

MEDIA_DIR = Path(__file__).resolve().parent.parent.parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)

# Every upload in the app is a photo (KYC docs, selfies, portfolio, designs,
# avatars, CMS images) - restricting to real, decodable raster images here
# blocks uploading e.g. an .svg or .html file with embedded script that
# would otherwise be served back (stored XSS), and a content-based
# extension instead of trusting the client's filename.
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
    )


def _validate_image(content: bytes) -> str:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File too large - max {settings.max_upload_size_mb}MB"
        )
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    try:
        with Image.open(BytesIO(content)) as img:
            img.verify()
            fmt = img.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File isn't a valid image") from exc

    ext = ALLOWED_IMAGE_FORMATS.get(fmt)
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported image format: {fmt}")
    return ext


def save_upload(content: bytes, folder: str) -> str:
    ext = _validate_image(content)
    key = f"{folder}/{uuid.uuid4().hex}{ext}"

    if settings.s3_bucket:
        client = _s3_client()
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ACL="public-read")
        base = settings.s3_public_base_url.rstrip("/")
        return f"{base}/{key}"

    dest = MEDIA_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return f"/media/{key}"
