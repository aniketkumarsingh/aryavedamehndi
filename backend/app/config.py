from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" | "production" - gates the startup safety checks in
    # app.main (refuses to boot in production with dev-only settings still
    # active, e.g. the placeholder JWT secret or OTP dev-mode).
    app_env: str = "development"

    database_url: str = "postgresql+psycopg://aryamehndi_app:changeme@localhost:5432/aryamehndi"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    otp_dev_mode: bool = True
    msg91_auth_key: str = ""
    msg91_sender_id: str = "ARYAMH"
    msg91_otp_template_id: str = ""

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # Exotel (or compatible) masked-calling / call-masking provider - used
    # so consumer and artist can call each other without either side
    # seeing the other's real phone number (Uber-style). Leave blank to
    # run in dev-stub mode (see app/services/telephony.py).
    exotel_sid: str = ""
    exotel_token: str = ""
    exotel_subdomain: str = "api.exotel.com"
    exotel_virtual_number: str = ""

    google_maps_api_key: str = ""

    # Secret for Razorpay webhooks (Dashboard -> Settings -> Webhooks), so
    # payments are recorded even if the customer's browser never reports back.
    razorpay_webhook_secret: str = ""

    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_public_base_url: str = ""

    # Public addresses, used in links that leave the site (ad product feeds,
    # notifications): the website, and the API that serves /media files.
    public_site_url: str = "https://www.aryavedamehndi.com"
    public_api_url: str = "http://localhost:8000"

    design_match_threshold: int = 90

    platform_fee_mode: str = "percent"  # "percent" or "flat"
    platform_fee_percent: float = 10
    platform_fee_flat: float = 0

    cors_origins: str = "http://localhost:3000"

    max_upload_size_mb: int = 8

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
