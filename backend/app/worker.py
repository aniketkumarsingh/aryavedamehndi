"""Background worker: runs queued jobs and schedules periodic tasks.

    venv/bin/python -m app.worker          # run forever (production)
    venv/bin/python -m app.worker --once   # drain what's due, then exit

Run at least one worker alongside the API in every environment that takes
payments. Several can run at once; they never pick up the same job.
"""

import argparse
import logging
import os
import signal
import socket
import time

from app import tasks  # noqa: F401 - registers every job handler and periodic task
from app.core.logging import configure_logging
from app.core.observability import init_sentry
from app.services.jobs import enqueue_periodic, requeue_stuck, run_due_jobs

log = logging.getLogger("app.worker")
_stopping = False


def _stop(signum, frame):  # noqa: ARG001
    global _stopping
    _stopping = True
    log.info("worker stopping after the current batch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="run due jobs and exit")
    parser.add_argument("--idle-sleep", type=float, default=2.0, help="seconds to wait when nothing is due")
    args = parser.parse_args()

    configure_logging("worker")
    init_sentry("worker")
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker %s started", worker_id)

    last_housekeeping = 0.0
    while not _stopping:
        if time.monotonic() - last_housekeeping > 30:
            enqueue_periodic()
            if stuck := requeue_stuck():
                log.warning("requeued %s stuck jobs", stuck)
            last_housekeeping = time.monotonic()
        ran = run_due_jobs(worker_id)
        if args.once and ran == 0:
            break
        if ran == 0:
            time.sleep(args.idle_sleep)
    log.info("worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
