import logging
import posixpath
import re
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import DEFAULT_JWT_SECRET, get_settings
from app.routers import (
    admin,
    artists,
    auth,
    bookings,
    bulk_orders,
    chat,
    cms,
    designs,
    favorites,
    notifications,
    packages,
    payments,
    pricing,
    product_reviews,
    referrals,
    reviews,
    seo_pages,
    shop,
    admin_payments,
    growth,
    returns,
    shipping,
    users,
    webhooks,
)
from app.core.logging import configure_logging, order_id_var, request_id_var, user_id_var
from app.core.observability import init_sentry
from app.services.storage import MEDIA_DIR, PRIVATE_URL_PREFIX, verify_media_signature

settings = get_settings()


def _check_production_safety() -> None:
    """Refuses to boot with dev-only settings if APP_ENV=production, rather
    than silently running an insecure configuration in the wild - e.g. the
    placeholder JWT secret (which would let anyone forge tokens) or OTP
    dev-mode (which hands out the login code in the API response)."""
    if settings.app_env != "production":
        return
    problems = []
    known_placeholders = {DEFAULT_JWT_SECRET, "change-this-to-a-long-random-string"}
    if settings.jwt_secret in known_placeholders or len(settings.jwt_secret) < 32:
        problems.append("JWT_SECRET looks like a placeholder or is too short - set a long (32+ char) random value")
    if settings.otp_dev_mode:
        problems.append("OTP_DEV_MODE is true - OTP codes are handed back in the API response")
    if "*" in settings.cors_origin_list:
        problems.append("CORS_ORIGINS allows '*' - restrict it to your real frontend origin(s)")
    # Without these the payment and SMS clients fall back to dev stubs: any
    # made-up payment would verify as paid, and OTPs would only be printed.
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        problems.append("RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are empty - payments would auto-verify without real money")
    if not settings.razorpay_webhook_secret:
        problems.append("RAZORPAY_WEBHOOK_SECRET is empty - payments made after a customer closes the page would be missed")
    if not (settings.msg91_auth_key and settings.msg91_otp_template_id):
        problems.append("MSG91_AUTH_KEY/MSG91_OTP_TEMPLATE_ID are empty - login OTPs would never be sent")
    if problems:
        raise RuntimeError(
            "Refusing to start with APP_ENV=production while insecure dev settings are active:\n- "
            + "\n- ".join(problems)
        )


_check_production_safety()
configure_logging("api")
init_sentry("api")
access_log = logging.getLogger("app.access")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
ORDER_IN_PATH = re.compile(r"/(?:orders|shop-orders|bulk-orders|bookings)/([0-9a-f]{8}-[0-9a-f-]{27})")
QUIET_PATHS = ("/health", "/health/ready")

app = FastAPI(title="AryaVeda Mehndi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Normalised + lowercased so "/media//kyc/", "/media/./kyc/" or
    # "/media/KYC/" (case-insensitive disks) can't slip past the check.
    canonical_path = posixpath.normpath(request.url.path).lower()
    if canonical_path.startswith(PRIVATE_URL_PREFIX):
        # KYC documents need a valid, unexpired signature - see
        # app/services/storage.py sign_media_url.
        if not verify_media_signature(canonical_path, request.query_params.get("exp"), request.query_params.get("sig")):
            return Response(status_code=404)
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # camera=(self) - the consumer profile selfie uses getUserMedia
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=()"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Outermost: gives every request an id (kept from Caddy/the client when
    sane), tags log lines with it, the user and the order, and writes one
    access line per request - a warning when slower than SLOW_REQUEST_MS."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
    match = ORDER_IN_PATH.search(request.url.path)
    tokens = [request_id_var.set(request_id), order_id_var.set(match.group(1) if match else None), user_id_var.set(None)]
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        user_id = getattr(request.state, "user_id", None)
        extra = {"method": request.method, "path": request.url.path, "status": status_code, "duration_ms": duration_ms, "user_id": user_id}
        if duration_ms > settings.slow_request_ms:
            access_log.warning("slow request", extra=extra)
        elif request.url.path not in QUIET_PATHS or status_code >= 400:
            access_log.info("request", extra=extra)
        for var, token in zip((request_id_var, order_id_var, user_id_var), tokens):
            var.reset(token)


app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(favorites.router)
app.include_router(artists.router)
app.include_router(packages.router)
app.include_router(designs.router)
app.include_router(designs.artist_router)
app.include_router(designs.admin_router)
app.include_router(bookings.router)
app.include_router(bulk_orders.router)
app.include_router(bulk_orders.admin_router)
app.include_router(pricing.router)
app.include_router(chat.router)
app.include_router(payments.router)
app.include_router(shop.router)
app.include_router(webhooks.router)
app.include_router(admin_payments.router)
app.include_router(shipping.router)
app.include_router(shipping.admin_router)
app.include_router(returns.router)
app.include_router(returns.admin_router)
app.include_router(growth.router)
app.include_router(growth.admin_router)
app.include_router(referrals.router)
app.include_router(referrals.admin_router)
app.include_router(reviews.router)
app.include_router(product_reviews.router)
app.include_router(product_reviews.admin_router)
app.include_router(seo_pages.router)
app.include_router(seo_pages.admin_router)
app.include_router(cms.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    """Liveness: the process is up. Cheap, no database - for container
    restarts. Use /health/ready for monitoring."""
    return {"status": "ok", "release": settings.git_sha or None}


@app.get("/health/ready")
def readiness_check():
    """Readiness for uptime monitors: 200 when the database answers and the
    worker is keeping up (and backups are recent), 503 with the reasons
    otherwise."""
    from fastapi.responses import JSONResponse

    from app.services.health import readiness

    report = readiness()
    return JSONResponse(report, status_code=200 if report["status"] == "ok" else 503)
