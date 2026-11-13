"""Claim queued jobs until stopped. Used by `python -m app.worker`."""

import time

from app.services.jobs import claim_next_job_id, execute_job, requeue_stale


def main() -> None:
    requeue_stale()
    while True:
        job_id = claim_next_job_id()
        if job_id:
            execute_job(job_id)
        else:
            time.sleep(0.8)


if __name__ == "__main__":
    main()
