from app.config import get_settings

settings = get_settings()


def compute_platform_fee(agreed_price: float) -> float:
    if settings.platform_fee_mode == "flat":
        return round(settings.platform_fee_flat, 2)
    return round(agreed_price * settings.platform_fee_percent / 100, 2)
