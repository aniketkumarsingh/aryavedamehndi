import pytest

import app.main as main
from app.services import telephony


def _prod(monkeypatch, **overrides):
    values = {
        "app_env": "production",
        "jwt_secret": "x" * 40,
        "otp_dev_mode": False,
        "cors_origins": "https://www.aryavedamehndi.com",
        "razorpay_key_id": "rzp_live_x",
        "razorpay_key_secret": "secret",
        "msg91_auth_key": "key",
        "msg91_otp_template_id": "tpl",
        "razorpay_webhook_secret": "whsec",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(main.settings, key, value)


def test_production_boots_with_real_settings(monkeypatch):
    _prod(monkeypatch)
    main._check_production_safety()


@pytest.mark.parametrize("field", ["razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret", "msg91_auth_key", "msg91_otp_template_id"])
def test_production_refuses_without_payment_or_sms_keys(monkeypatch, field):
    _prod(monkeypatch, **{field: ""})
    with pytest.raises(RuntimeError):
        main._check_production_safety()


def test_no_fake_call_number_in_production(monkeypatch):
    monkeypatch.setattr(telephony.settings, "app_env", "production")
    monkeypatch.setattr(telephony.settings, "exotel_sid", "")
    assert telephony.provision_masked_number("abc", "9800000000", "9811111111") == (None, None)
