"""
In-process daily scheduler.

There is no external cron/systemd timer/CI schedule wired to this app
anywhere (single EC2 instance running one Docker container behind nginx —
see docs/DEPLOYMENT.md) — `/api/v1/cron/snapshot-stats` existed as an
endpoint but nothing ever called it, so Instagram stats never refreshed
automatically and `creator_stats_history` stayed permanently empty. This
runs the same job in-process instead, so it works the moment the container
is running, with no server-side setup required.

Safe as a single in-process job because the app runs as a single uvicorn
worker (see Dockerfile CMD — no `--workers` flag). If that ever changes to
multiple workers/processes, this would need a DB-based lock (e.g. a
Postgres advisory lock) to avoid running the job once per worker.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services import creator_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

_JOB_ID = "daily_instagram_stats_refresh"


async def _run_daily_instagram_refresh() -> None:
    try:
        result = await creator_service.refresh_all_instagram_stats()
        logger.info("Daily Instagram stats refresh complete: %s", result)
    except Exception:
        logger.exception("Daily Instagram stats refresh job crashed")


def start_scheduler() -> None:
    """Idempotent — safe to call more than once (e.g. test setup)."""
    if scheduler.running:
        return
    scheduler.add_job(
        _run_daily_instagram_refresh,
        CronTrigger(hour=3, minute=0),  # 03:00 UTC — low-traffic window
        id=_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started — daily Instagram stats refresh runs at 03:00 UTC")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
