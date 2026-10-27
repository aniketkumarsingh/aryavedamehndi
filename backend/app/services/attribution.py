"""Marketing attribution: where customers and their orders came from.

The browser keeps the first and latest landing (UTM tags, ad click ids,
referral code) and sends them with sign-in and with each order, booking or
bulk request. The user keeps the first touch; each order keeps its own
latest touch and a one-word `source` for reporting.
"""

from pydantic import BaseModel, Field

KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid", "fbp", "fbc",
        "ga_client_id", "referrer", "landing_path", "ref", "captured_at")


class AttributionIn(BaseModel):
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=150)
    utm_content: str | None = Field(default=None, max_length=150)
    utm_term: str | None = Field(default=None, max_length=150)
    gclid: str | None = Field(default=None, max_length=200)
    fbclid: str | None = Field(default=None, max_length=300)
    fbp: str | None = Field(default=None, max_length=100)  # Meta browser id (_fbp cookie)
    fbc: str | None = Field(default=None, max_length=400)  # Meta click id (_fbc cookie)
    ga_client_id: str | None = Field(default=None, max_length=100)  # from the _ga cookie
    referrer: str | None = Field(default=None, max_length=300)
    landing_path: str | None = Field(default=None, max_length=300)
    ref: str | None = Field(default=None, max_length=16)  # referral code from ?ref=
    captured_at: str | None = Field(default=None, max_length=40)


def clean(data: AttributionIn | dict | None) -> dict | None:
    if data is None:
        return None
    raw = data.model_dump() if isinstance(data, AttributionIn) else data
    out = {k: str(raw[k]).strip()[:400] for k in KEYS if raw.get(k)}
    return out or None


def source_of(attribution: dict | None, referral: bool = False) -> str:
    if referral:
        return "referral"
    a = attribution or {}
    if a.get("utm_source"):
        return a["utm_source"].lower()[:40]
    if a.get("gclid"):
        return "google_ads"
    if a.get("fbclid") or a.get("fbc"):
        return "meta_ads"
    if a.get("ref"):
        return "referral"
    return "direct"


def remember_first_touch(user, data: AttributionIn | dict | None) -> None:
    touch = clean(data)
    if touch and not user.attribution:
        user.attribution = touch
