"""Admin-tunable business settings, read at request time so changes from
the admin panel take effect immediately. Each key falls back to its .env
value (app/config.py) until an admin saves an override."""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.platform_settings import PlatformSetting

settings = get_settings()


def _defaults() -> dict:
    return {
        "platform_fee_mode": settings.platform_fee_mode,
        "platform_fee_percent": settings.platform_fee_percent,
        "platform_fee_flat": settings.platform_fee_flat,
        "design_match_threshold": settings.design_match_threshold,
        "strikes_before_suspension": 3,
        "checkin_flag_distance_m": 500,
    }


def get_platform_settings(db: Session) -> dict:
    values = _defaults()
    for row in db.query(PlatformSetting).filter(PlatformSetting.key.in_(values.keys())).all():
        values[row.key] = row.value
    return values


def update_platform_settings(db: Session, changes: dict) -> dict:
    """Upserts only the keys present in `changes` (already validated by
    the caller's schema). Doesn't commit."""
    for key, value in changes.items():
        row = db.get(PlatformSetting, key)
        if row is None:
            db.add(PlatformSetting(key=key, value=value))
        else:
            row.value = value
    db.flush()
    return get_platform_settings(db)
