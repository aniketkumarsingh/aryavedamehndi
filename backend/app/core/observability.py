"""Error tracking (Sentry) for the API and the worker. Off unless
SENTRY_DSN is set. Errors are tagged with the component and the release
(GIT_SHA), and personal data isn't sent: no request bodies, cookies or IPs."""

import logging

from app.config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


def init_sentry(component: str) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.git_sha or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
    )
    sentry_sdk.set_tag("component", component)
    log.info("Sentry error tracking on (%s, release %s)", component, settings.git_sha or "unknown")
    return True


def capture(exc: BaseException, **tags) -> None:
    """Reports a handled exception (e.g. a job that gave up) if Sentry is on."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        for key, value in tags.items():
            scope.set_tag(key, value)
        sentry_sdk.capture_exception(exc)
