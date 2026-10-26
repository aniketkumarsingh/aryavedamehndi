from datetime import datetime, timedelta

from app.core.time import utcnow
from app.database import SessionLocal
from app.models.job import Job
from app.models.notification import Notification
from app.services import jobs
from tests.conftest import auth_headers, make_user, run_jobs


def _enqueue(kind, payload=None, **kw):
    with SessionLocal() as s:
        jobs.enqueue(s, kind, payload, **kw)
        s.commit()


def test_dedupe_key_creates_one_job(db):
    _enqueue("jobs.cleanup", dedupe_key="same")
    _enqueue("jobs.cleanup", dedupe_key="same")
    assert db.query(Job).count() == 1


def test_enqueue_is_part_of_the_callers_transaction(db):
    with SessionLocal() as s:
        jobs.enqueue(s, "jobs.cleanup")
        s.rollback()
    assert db.query(Job).count() == 0


def test_failing_job_backs_off_then_dies_and_alerts_admins(db):
    admin = make_user(db, role="admin")
    calls = []

    @jobs.job_handler("test.always_fails")
    def always_fails(session, payload):
        calls.append(1)
        raise RuntimeError("boom")

    _enqueue("test.always_fails", max_attempts=2)
    run_jobs()
    job = db.query(Job).one()
    assert job.status == "queued" and job.attempts == 1 and job.run_at > utcnow()

    job.run_at = utcnow() - timedelta(seconds=1)
    db.commit()
    run_jobs()
    db.expire_all()
    job = db.query(Job).one()
    assert job.status == "dead" and job.attempts == 2 and "boom" in job.last_error
    assert len(calls) == 2
    assert db.query(Notification).filter(Notification.user_id == admin.id, Notification.title == "Background job failed").count() == 1


def test_admin_retries_a_dead_job(client, db):
    admin = make_user(db, role="admin")

    @jobs.job_handler("test.flaky")
    def flaky(session, payload):
        if payload.get("fail"):
            raise RuntimeError("nope")
        return "ok"

    _enqueue("test.flaky", {"fail": True}, max_attempts=1)
    run_jobs()
    job = db.query(Job).one()
    assert job.status == "dead"
    assert client.get("/admin/payments/jobs", headers=auth_headers(admin)).json()[0]["id"] == str(job.id)

    job.payload = {"fail": False}
    db.commit()
    assert client.post(f"/admin/payments/jobs/{job.id}/retry", headers=auth_headers(admin)).json()["status"] == "queued"
    run_jobs()
    db.expire_all()
    assert db.get(Job, job.id).status == "done"
    assert client.post(f"/admin/payments/jobs/{job.id}/retry", headers=auth_headers(admin)).status_code == 400


def test_unknown_job_kind_is_recorded_not_lost(db):
    _enqueue("test.no_such_handler", max_attempts=1)
    run_jobs()
    job = db.query(Job).one()
    assert job.status == "dead" and "No handler" in job.last_error


def test_crashed_worker_jobs_are_requeued(db):
    _enqueue("jobs.cleanup")
    job = db.query(Job).one()
    job.status, job.locked_at, job.locked_by = "running", utcnow() - timedelta(hours=1), "dead-worker"
    db.commit()
    assert jobs.requeue_stuck() == 1
    db.expire_all()
    assert db.get(Job, job.id).status == "queued"


def test_periodic_tasks_run_once_per_slot(db):
    now = datetime(2026, 10, 26, 12, 0, 0)
    jobs.enqueue_periodic(now)
    jobs.enqueue_periodic(now + timedelta(seconds=30))  # same slots, e.g. a second worker
    kinds = sorted(k for (k,) in db.query(Job.kind).all())
    assert kinds == sorted(p.kind for p in jobs.PERIODIC)
    jobs.enqueue_periodic(now + timedelta(minutes=5))  # next 5-minute slot
    assert db.query(Job).filter(Job.kind == "shop.release_unpaid").count() == 2


def test_daily_reconciliation_slot_starts_at_3am_ist(db):
    jobs.enqueue_periodic(datetime(2026, 10, 26, 22, 0, 0))  # 03:30 IST on the 27th
    job = db.query(Job).filter(Job.kind == "payments.reconcile").one()
    assert job.run_at == datetime(2026, 10, 26, 21, 30, 0)  # 03:00 IST
