from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime - every DateTime column in this
    schema stores naive UTC. Replaces the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
