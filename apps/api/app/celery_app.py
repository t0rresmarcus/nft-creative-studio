"""Optional Celery entrypoint. Enable with CELERY_ENABLED=1 and REDIS_URL."""

from app.config import settings


def run_job_task(*_args, **_kwargs):
    raise RuntimeError("Celery is not enabled")


if settings.celery_enabled and settings.redis_url:
    from celery import Celery

    celery = Celery("nftstudio", broker=settings.redis_url, backend=settings.redis_url)

    @celery.task(name="jobs.run")
    def run_job_task(job_id: str):  # type: ignore[no-redef]
        from app.services.jobs import execute_job

        execute_job(job_id)
