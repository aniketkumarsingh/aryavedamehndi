import posixpath

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
    reviews,
    shop,
    admin_payments,
    growth,
    returns,
    shipping,
    users,
    webhooks,
)
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
init_sentry("api")

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
app.include_router(reviews.router)
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
