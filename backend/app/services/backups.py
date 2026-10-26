"""Nightly database backups.

ops.backup_database (daily, 01:30 IST) runs pg_dump in custom format,
checks the archive is readable (pg_restore --list), then stores it:
- in S3/R2 under backups/ (private) when BACKUP_S3_BUCKET or S3_BUCKET is
  set - the right choice in production, off the server;
- otherwise in BACKUP_DIR on disk (dev, or a mounted volume).
Backups older than BACKUP_RETENTION_DAYS are deleted. Invoices and credit
notes are legal records, so a failed backup is retried and, if it keeps
failing, reported like any job that gives up.

Restore with scripts/restore_backup.sh (see the README's restore drill).
"""

import logging
import os
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import utcnow
from app.services.jobs import job_handler, periodic

log = logging.getLogger(__name__)
settings = get_settings()
PREFIX = "backups/"


def _pg_env() -> dict:
    """libpq connection settings from DATABASE_URL, via the environment so
    the password never shows up in the process list."""
    url = make_url(settings.database_url)
    env = dict(os.environ)
    env.update({
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database or "",
    })
    return env


def _bucket() -> str:
    return settings.backup_s3_bucket or settings.s3_bucket


def dump(target: Path) -> int:
    """Writes a verified custom-format dump; returns its size in bytes."""
    env = _pg_env()
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", f"--file={target}"],
                   env=env, check=True, capture_output=True, timeout=3600)
    listing = subprocess.run(["pg_restore", "--list", str(target)], check=True, capture_output=True, timeout=600)
    if b"TABLE DATA" not in listing.stdout:
        raise RuntimeError("Backup archive has no table data - refusing to keep it")
    return target.stat().st_size


def run_backup(now=None) -> dict:
    now = now or utcnow()
    name = f"aryaveda-{now:%Y%m%d-%H%M%S}.dump"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        size = dump(path)
        if _bucket():
            from app.services.storage import _s3_client

            client = _s3_client()
            client.upload_file(str(path), _bucket(), PREFIX + name, ExtraArgs={"ServerSideEncryption": "AES256"} if not settings.s3_endpoint_url else None)
            removed = _prune_s3(client, now)
            where = f"s3://{_bucket()}/{PREFIX}{name}"
        else:
            folder = Path(settings.backup_dir)
            folder.mkdir(parents=True, exist_ok=True)
            final = folder / name
            final.write_bytes(path.read_bytes())
            removed = _prune_dir(folder, now)
            where = str(final)
    log.info("backup written to %s (%s bytes, %s old removed)", where, size, removed)
    return {"location": where, "bytes": size, "removed": removed}


def _prune_s3(client, now) -> int:
    cutoff = now - timedelta(days=settings.backup_retention_days)
    removed = 0
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=PREFIX):
        for obj in page.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < cutoff:
                client.delete_object(Bucket=_bucket(), Key=obj["Key"])
                removed += 1
    return removed


def _prune_dir(folder: Path, now) -> int:
    cutoff = (now - timedelta(days=settings.backup_retention_days)).timestamp()
    removed = 0
    for file in folder.glob("aryaveda-*.dump"):
        if file.stat().st_mtime < cutoff:
            file.unlink()
            removed += 1
    return removed


@job_handler("ops.backup_database")
def backup_job(db: Session, payload: dict) -> str:
    result = run_backup()
    return f"{result['location']} ({result['bytes'] // 1024} KB)"


periodic("ops.backup_database", timedelta(days=1), offset=timedelta(hours=20))  # 01:30 IST
