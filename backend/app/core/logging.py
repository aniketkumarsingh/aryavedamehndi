"""Structured logs. In production every line is one JSON object carrying
the request id (also returned as the X-Request-ID header and accepted from
Caddy), the signed-in user, and the order or job being worked on, so one
customer's problem can be followed across the API and the worker:

    docker compose logs api worker | grep '"order_id": "3f2c..."'

LOG_FORMAT=json|text overrides the default (json when APP_ENV=production).
"""

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
order_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("order_id", default=None)
job_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job", default=None)

CONTEXT = {"request_id": request_id_var, "user_id": user_id_var, "order_id": order_id_var, "job": job_var}
# Extra fields a log call may pass, e.g. log.info("request", extra={"status": 200}).
EXTRA_FIELDS = ("method", "path", "status", "duration_ms", "service")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in CONTEXT.items():
            if not hasattr(record, name):
                setattr(record, name, var.get())
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for name in (*CONTEXT, *EXTRA_FIELDS):
            value = getattr(record, name, None)
            if value is not None and name not in line:
                line[name] = value
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        ctx = " ".join(f"{k}={getattr(record, k)}" for k in CONTEXT if getattr(record, k, None))
        return f"{base} [{ctx}]" if ctx else base


def configure_logging(service: str) -> None:
    from app.config import get_settings

    settings = get_settings()
    fmt = (os.environ.get("LOG_FORMAT") or ("json" if settings.app_env == "production" else "text")).lower()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter(service) if fmt == "json" else TextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    # Uvicorn's own loggers go through the same handler (access logs are
    # written by our middleware instead - run uvicorn with --no-access-log).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
