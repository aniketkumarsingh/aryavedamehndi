import uuid

from pydantic import BaseModel, Field


class RequestOtpIn(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)


class RequestOtpOut(BaseModel):
    sent_by_sms: bool
    dev_otp: str | None = None  # only populated when OTP_DEV_MODE=true


class AdminLoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)


class VerifyOtpIn(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=4, max_length=6)
    # role only matters on first signup; ignored for existing users
    role: str = Field(default="consumer")
    name: str | None = None
    gender: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    user_id: uuid.UUID
    role: str
    is_new_user: bool
