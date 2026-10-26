"""Masked calling (Uber/Ola-style number privacy) between consumer and
artist, so neither side ever sees the other's real phone number.

Real masked calling needs a telephony provider that supports number
masking / call bridging - Exotel is the most common choice for this in
India. Without EXOTEL_SID/EXOTEL_TOKEN/EXOTEL_VIRTUAL_NUMBER configured,
this runs in dev-stub mode: it returns a clearly-fake placeholder number
so the booking flow can be exercised end-to-end locally. Wiring up a real
Exotel (or similar) account turns this on - no other code needs to change.
"""

import uuid

import httpx

from app.config import get_settings

settings = get_settings()


def _configured() -> bool:
    return bool(settings.exotel_sid and settings.exotel_token and settings.exotel_virtual_number)


def provision_masked_number(booking_id: uuid.UUID, consumer_phone: str, artist_phone: str) -> tuple[str | None, str | None]:
    """Returns (masked_number, provider_ref) that both consumer and artist
    can dial to reach each other for this booking, with real numbers
    hidden from one another."""
    if not _configured():
        if settings.app_env == "production":
            # No number at all - the booking page hides the call button
            # rather than showing a fake one to real customers.
            return None, None
        # Dev-stub: a clearly-fake number, distinguishable from a real one,
        # so nothing in the UI accidentally looks like it actually works.
        return f"+91-DEV-{str(booking_id)[:8].upper()}", f"dev_mask_{booking_id}"

    # Exotel's "Call Masking" API creates a short-lived mapping between two
    # real numbers on a shared virtual (Exophone) number - either party
    # can then just dial that one virtual number to be bridged to the
    # other. Endpoint/param names should be double-checked against Exotel's
    # current API docs once real credentials are in place.
    url = (
        f"https://{settings.exotel_sid}:{settings.exotel_token}@{settings.exotel_subdomain}"
        f"/v1/Accounts/{settings.exotel_sid}/CustomerVirtualNumberMappings"
    )
    payload = {
        "VirtualNumber": settings.exotel_virtual_number,
        "CustomerNumber": consumer_phone,
        "AgentNumber": artist_phone,
        "CallType": "trunk-testcall",
    }
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, data=payload)
        resp.raise_for_status()
        data = resp.json()

    return settings.exotel_virtual_number, data.get("Mapping", {}).get("Sid", "")
