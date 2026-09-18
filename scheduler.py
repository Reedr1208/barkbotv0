"""
APScheduler-based cron scheduler for BarkBot.

All scraper, pipeline, and maintenance jobs run as in-process scheduled
tasks inside the Railway-hosted server.  Shelter jobs are defined
declaratively in jobs/shelter_registry.py.
"""

import asyncio
import logging
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED

logger = logging.getLogger("barkbot.scheduler")


@contextmanager
def _clean_argv():
    """Temporarily replace sys.argv so argparse inside job functions
    doesn't pick up uvicorn's CLI arguments."""
    saved = sys.argv
    sys.argv = ["scheduler"]
    try:
        yield
    finally:
        sys.argv = saved


# Global scheduler instance
scheduler = BackgroundScheduler(timezone="UTC")

# ── In-memory job execution tracking (for the admin dashboard) ──────
# Maps job_id → dict with start_time, end_time, status, error, duration_s
_job_runs: dict[str, dict] = {}        # last completed run per job
_running_jobs: dict[str, dict] = {}    # currently executing jobs
_lock = threading.Lock()


def _on_job_started(job_id: str, triggered_by: str = "scheduler"):
    """Record that a job has started executing."""
    now = datetime.now(timezone.utc)
    with _lock:
        _running_jobs[job_id] = {
            "job_id": job_id,
            "started_at": now.isoformat(),
            "triggered_by": triggered_by,
        }


def _on_job_finished(job_id: str, success: bool, error_msg: str | None = None):
    """Record that a job has finished, update in-memory state, and write to DB."""
    now = datetime.now(timezone.utc)
    with _lock:
        started_info = _running_jobs.pop(job_id, {})
    started_at_str = started_info.get("started_at", now.isoformat())
    triggered_by = started_info.get("triggered_by", "scheduler")

    # Calculate duration
    try:
        started_at = datetime.fromisoformat(started_at_str)
        duration_s = round((now - started_at).total_seconds(), 1)
    except Exception:
        duration_s = 0

    run_record = {
        "job_id": job_id,
        "started_at": started_at_str,
        "finished_at": now.isoformat(),
        "status": "success" if success else "failed",
        "duration_s": duration_s,
        "error": error_msg,
        "triggered_by": triggered_by,
    }
    with _lock:
        _job_runs[job_id] = run_record

    # Write to Supabase scrape_runs (best-effort — don't crash if DB is down)
    try:
        from jobs.lib.db import get_supabase_client, now_iso
        client = get_supabase_client()
        payload = {
            "job_id": job_id,
            "triggered_by": triggered_by,
            "started_at": started_at_str,
            "finished_at": now.isoformat(),
            "status": "success" if success else "failed",
            "notes": error_msg[:500] if error_msg else None,
        }
        client.table("scrape_runs").insert(payload).execute()
    except Exception as e:
        logger.warning(f"Failed to write run record to DB for {job_id}: {e}")


def get_running_jobs() -> dict:
    """Return a copy of currently running jobs."""
    with _lock:
        return dict(_running_jobs)


def get_last_runs() -> dict:
    """Return a copy of last-completed run per job."""
    with _lock:
        return dict(_job_runs)


def _job_listener(event):
    """Log job execution results and update tracking state."""
    if event.exception:
        logger.error(f"Job {event.job_id} failed: {event.exception}")
        _on_job_finished(event.job_id, success=False, error_msg=str(event.exception))
    else:
        logger.info(f"Job {event.job_id} completed successfully.")
        _on_job_finished(event.job_id, success=True)


def _job_submitted_listener(event):
    """Track when a scheduled job starts executing."""
    _on_job_started(event.job_id, triggered_by="scheduler")


scheduler.add_listener(_job_submitted_listener, EVENT_JOB_SUBMITTED)
scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


# ──────────────────────────────────────────────────────────────────────
# Shelter jobs — driven by the registry in jobs/shelter_registry.py
# ──────────────────────────────────────────────────────────────────────

from jobs.shelter_registry import SHELTER_JOBS, run_shelter_job, _JOBS_BY_ID


# ──────────────────────────────────────────────────────────────────────
# Non-shelter job wrappers (these have unique logic, kept explicit)
# ──────────────────────────────────────────────────────────────────────

def _run_generate_prompts():
    from jobs.generate_prompts_job import run
    with _clean_argv():
        run()


def _run_cleanup_inactive_dogs():
    import importlib.util
    import os
    spec = importlib.util.spec_from_file_location(
        "cleanup_inactive_dogs",
        os.path.join(os.path.dirname(__file__), "jobs", "08_cleanup_inactive_dogs.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with _clean_argv():
        mod.main()


def _run_monitors():
    from monitors import run_all_monitors
    with _clean_argv():
        run_all_monitors()


# ──────────────────────────────────────────────────────────────────────
# Registry: maps job_id → callable
# Auto-generated from SHELTER_JOBS + explicit non-shelter entries
# ──────────────────────────────────────────────────────────────────────

JOB_REGISTRY = {
    entry["job_id"]: (lambda jid=entry["job_id"]: run_shelter_job(jid))
    for entry in SHELTER_JOBS
}
JOB_REGISTRY["generate_prompts"] = _run_generate_prompts
JOB_REGISTRY["cleanup_inactive_dogs"] = _run_cleanup_inactive_dogs
JOB_REGISTRY["monitors"] = _run_monitors


def run_job_by_id(job_id: str, triggered_by: str = "manual"):
    """Run a job synchronously by its ID. Used by manual trigger endpoints."""
    func = JOB_REGISTRY.get(job_id)
    if not func:
        raise ValueError(f"Unknown job: {job_id}")
    _on_job_started(job_id, triggered_by=triggered_by)
    try:
        func()
        _on_job_finished(job_id, success=True)
    except Exception as e:
        _on_job_finished(job_id, success=False, error_msg=str(e))
        raise


def setup_schedules():
    """Register all cron schedules with APScheduler."""

    # Shelter jobs — auto-registered from registry
    for entry in SHELTER_JOBS:
        job_id = entry["job_id"]
        scheduler.add_job(
            lambda jid=job_id: run_shelter_job(jid),
            CronTrigger.from_crontab(entry["cron"]),
            id=job_id,
            replace_existing=True,
        )

    # Non-shelter jobs
    scheduler.add_job(_run_generate_prompts, CronTrigger.from_crontab("*/30 * * * *"), id="generate_prompts", replace_existing=True)
    scheduler.add_job(_run_cleanup_inactive_dogs, CronTrigger.from_crontab("15 */4 * * *"), id="cleanup_inactive_dogs", replace_existing=True)
    scheduler.add_job(_run_monitors, CronTrigger.from_crontab("0 14 * * *"), id="monitors", replace_existing=True)

    logger.info(f"Registered {len(scheduler.get_jobs())} scheduled jobs.")


def get_scheduler_status():
    """Return the current status of all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.isoformat() if next_run else None,
            "trigger": str(job.trigger),
        })
    return {
        "running": scheduler.running,
        "job_count": len(jobs),
        "jobs": sorted(jobs, key=lambda j: j["next_run"] or ""),
    }
