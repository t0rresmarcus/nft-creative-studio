"""Database-backed job queue. A worker process claims rows; tests can run them inline."""

from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Job
from app.security import utcnow

logger = logging.getLogger("nftstudio.jobs")
_stop = threading.Event()


def execute_job(job_id: str) -> None:
    from app.models import Collection, Project, User, Workflow
    from app.services.batch import run_batch
    from app.services.collections import render_collection
    from app.services.ipfs import pin_collection

    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status not in {"running", "queued"}:
            return
        job.status = "running"
        job.updated_at = utcnow()
        db.commit()
        try:
            project = db.get(Project, job.project_id)
            payload = job.payload or {}
            if job.kind == "render_collection":
                collection = db.get(Collection, payload["collection_id"])
                report = render_collection(db, collection, project, job)
                job = db.get(Job, job_id)
                job.result = {"report": report}
            elif job.kind == "batch":
                workflow = db.get(Workflow, payload["workflow_id"])
                result = run_batch(
                    db,
                    workflow,
                    payload.get("asset_ids") or [],
                    int(payload.get("seed") or 1),
                    bool(payload.get("dry_run")),
                    project.name,
                    job.user_id,
                    job,
                )
                job = db.get(Job, job_id)
                job.result = result
            elif job.kind == "ipfs":
                collection = db.get(Collection, payload["collection_id"])
                user = db.get(User, job.user_id)
                result = pin_collection(db, collection, project, user, job)
                job = db.get(Job, job_id)
                job.result = result
            else:
                raise RuntimeError(f"Unknown job {job.kind}")
            job.status = "succeeded"
            job.progress = 1
            job.error = None
            job.updated_at = utcnow()
            db.commit()
        except Exception as exc:
            logger.exception("job %s failed", job_id)
            db.rollback()
            job = db.get(Job, job_id)
            job.error = str(exc)
            job.updated_at = utcnow()
            if job.attempts < job.max_attempts:
                job.status = "queued"
            else:
                job.status = "failed"
            db.commit()
    finally:
        db.close()


def enqueue(db: Session, job: Job) -> Job:
    job.status = "queued"
    job.updated_at = utcnow()
    db.commit()
    db.refresh(job)
    if settings.force_sync:
        for _ in range(job.max_attempts):
            db.refresh(job)
            if job.status != "queued":
                break
            job.status = "running"
            job.attempts += 1
            job.updated_at = utcnow()
            db.commit()
            execute_job(job.id)
            db.refresh(job)
        return job
    if settings.celery_enabled and settings.redis_url:
        try:
            from app.celery_app import run_job_task

            run_job_task.delay(job.id)
        except Exception as exc:
            logger.warning("Celery enqueue failed, the embedded worker can still claim the job: %s", exc)
    return job


def claim_next_job_id() -> str | None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.status == "queued").order_by(Job.created_at.asc()).first()
        if job is None:
            return None
        updated = (
            db.query(Job)
            .filter(Job.id == job.id, Job.status == "queued")
            .update({"status": "running", "attempts": job.attempts + 1, "updated_at": utcnow()}, synchronize_session=False)
        )
        db.commit()
        return job.id if updated else None
    finally:
        db.close()


def requeue_stale() -> None:
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(minutes=20)
        db.query(Job).filter(Job.status == "running", Job.updated_at < cutoff).update(
            {"status": "queued", "updated_at": utcnow()},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _loop() -> None:
    requeue_stale()
    while not _stop.is_set():
        job_id = claim_next_job_id()
        if job_id:
            execute_job(job_id)
        else:
            time.sleep(0.8)


def start_worker() -> threading.Event:
    _stop.clear()
    thread = threading.Thread(target=_loop, name="nft-worker", daemon=True)
    thread.start()
    return _stop


def create_job(db: Session, *, project_id: str, user_id: str | None, kind: str, payload: dict) -> Job:
    job = Job(project_id=project_id, user_id=user_id, kind=kind, status="queued", payload=payload, result=None)
    db.add(job)
    db.flush()
    return job
