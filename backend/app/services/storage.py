"""Stores uploaded images (portfolios, KYC docs, reference designs,
completed-work photos, CMS media).

Uses S3-compatible object storage when configured; otherwise falls back to
local disk under ./media, served by FastAPI's static file mount, so the
whole app runs with zero external accounts during local development.
"""

import hashlib
import hmac
import re
import time
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

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

# KYC documents (Aadhaar/PAN/address proof, KYC selfie) are never publicly
# readable. The stored value is a bare path/key; whoever is allowed to see
# it (the artist themself, admins) gets a short-lived signed URL from
# sign_media_url - a signed "/media/kyc/..." URL checked by the middleware
# in app/main.py for local disk, or an S3 presigned URL.
PRIVATE_FOLDERS = {"kyc"}
PRIVATE_URL_PREFIX = "/media/kyc/"
S3_PRIVATE_SCHEME = "s3private://"
SIGNED_URL_TTL_SECONDS = 3600


def _media_signature(path: str, expires: int) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"{path}:{expires}".encode(), hashlib.sha256).hexdigest()


def sign_media_url(url: str | None) -> str | None:
    if not url:
        return url
    if url.startswith(PRIVATE_URL_PREFIX):
        expires = int(time.time()) + SIGNED_URL_TTL_SECONDS
        return f"{url}?{urlencode({'exp': expires, 'sig': _media_signature(url, expires)})}"
    if url.startswith(S3_PRIVATE_SCHEME):
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": url.removeprefix(S3_PRIVATE_SCHEME)},
            ExpiresIn=SIGNED_URL_TTL_SECONDS,
        )
    return url


def verify_media_signature(path: str, expires: str | None, signature: str | None) -> bool:
    if not expires or not signature or not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(_media_signature(path, int(expires)), signature)


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


DISPLAY_PX = 1600  # long edge of the light copy shown on pages


def save_image_variants(content: bytes, folder: str, display_px: int = DISPLAY_PX, name: str | None = None) -> tuple[str, str | None]:
    """Stores a large photo twice: a light display copy (long edge
    `display_px`, JPEG) for pages and thumbnails, and the original at full
    resolution for zooming. Returns (display_url, hd_url); hd_url is None
    when the original is already small enough to serve as-is. With `name`,
    the files are <name>.jpg and <name>-hd.jpg (see save_upload)."""
    _validate_image(content)
    with Image.open(BytesIO(content)) as img:
        if max(img.size) <= display_px * 1.25:
            return save_upload(content, folder, name), None
        img = img.convert("RGB")
        img.thumbnail((display_px, display_px), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
    return save_upload(buf.getvalue(), folder, name), save_upload(content, folder, name and f"{name}-hd")


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def save_upload(content: bytes, folder: str, name: str | None = None) -> str:
    """Stores an upload under a random name, or under `name` (lowercase
    letters, digits and dashes, no extension) when the caller picks a
    stable one - an existing file of that name is replaced."""
    ext = _validate_image(content)
    if name is not None and not SAFE_NAME.match(name):
        raise ValueError(f"unsafe file name: {name!r}")
    key = f"{folder}/{name or uuid.uuid4().hex}{ext}"

    if settings.s3_bucket:
        client = _s3_client()
        if folder in PRIVATE_FOLDERS:
            client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ACL="private")
            return f"{S3_PRIVATE_SCHEME}{key}"
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ACL="public-read")
        base = settings.s3_public_base_url.rstrip("/")
        return f"{base}/{key}"

    dest = MEDIA_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return f"/media/{key}"
