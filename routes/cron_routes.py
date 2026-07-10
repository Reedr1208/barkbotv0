"""
Manual cron trigger endpoints + scheduler status.

Allows you to run any cron job on-demand via HTTP POST, and check the
scheduler status via GET. All endpoints require Bearer token auth
using the CRON_SECRET env var.
"""

import os
import logging
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from scheduler import JOB_REGISTRY, run_job_by_id, get_scheduler_status

router = APIRouter()
logger = logging.getLogger("barkbot.cron_routes")


def _check_auth(request: Request) -> bool:
    """Verify Bearer token matches CRON_SECRET."""
    cron_secret = os.environ.get("CRON_SECRET")
    if not cron_secret:
        # No secret configured — allow all requests (dev mode)
        return True
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return False
    token = auth.split(" ", 1)[1]
    return token == cron_secret


@router.get("/api/cron/status")
async def cron_status(request: Request):
    """Return the current status of the scheduler and all registered jobs."""
    if not _check_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return JSONResponse(content=get_scheduler_status())


@router.get("/api/cron/jobs")
async def cron_jobs_list(request: Request):
    """Return the list of available job IDs that can be manually triggered."""
    if not _check_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return JSONResponse(content={"jobs": sorted(JOB_REGISTRY.keys())})


@router.post("/api/cron/{job_id}")
async def trigger_cron(job_id: str, request: Request):
    """Manually trigger a cron job by its ID. Runs in a background thread."""
    if not _check_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    if job_id not in JOB_REGISTRY:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown job: {job_id}", "available_jobs": sorted(JOB_REGISTRY.keys())}
        )

    # Run the job in a background thread so the HTTP response returns immediately
    def _run():
        try:
            logger.info(f"Manually triggered job: {job_id}")
            run_job_by_id(job_id)
            logger.info(f"Manual job {job_id} completed successfully.")
        except Exception as e:
            logger.error(f"Manual job {job_id} failed: {e}")

    thread = threading.Thread(target=_run, name=f"manual-{job_id}", daemon=True)
    thread.start()

    return JSONResponse(content={
        "status": "triggered",
        "job_id": job_id,
        "message": f"Job '{job_id}' started in background. Check logs for progress."
    })
