"""
Admin dashboard routes for cron job monitoring.

Provides a password-protected web dashboard at /admin/crons for:
- Viewing all cron jobs with their schedules, statuses, and run history
- Manually triggering jobs
- Monitoring system health

Authentication is via a simple password (ADMIN_PASSWORD env var) stored
in a session cookie.
"""

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse

from scheduler import (
    JOB_REGISTRY,
    run_job_by_id,
    get_scheduler_status,
    get_running_jobs,
    get_last_runs,
    scheduler,
)

router = APIRouter()
logger = logging.getLogger("barkbot.admin")

# ── Session management ──────────────────────────────────────────────
# Simple token-based sessions: cookie "admin_session" → validated against
# a server-side set of valid tokens.

_valid_sessions: set[str] = set()
_session_lock = threading.Lock()
_SERVER_START_TIME = datetime.now(timezone.utc)


def _check_admin_auth(request: Request) -> bool:
    """Check if the request has a valid admin session cookie."""
    token = request.cookies.get("admin_session")
    if not token:
        return False
    with _session_lock:
        return token in _valid_sessions


def _create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    with _session_lock:
        _valid_sessions.add(token)
    return token


# ── Auth endpoints ──────────────────────────────────────────────────

@router.get("/admin/login")
async def admin_login_page():
    """Serve the login page."""
    login_path = os.path.join(os.path.dirname(__file__), "..", "public", "admin", "login.html")
    if os.path.isfile(login_path):
        return FileResponse(login_path, media_type="text/html")
    return HTMLResponse("<h1>Login page not found</h1>", status_code=500)


@router.post("/admin/login")
async def admin_login(request: Request):
    """Authenticate with password and set session cookie."""
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        return JSONResponse(
            status_code=500,
            content={"error": "ADMIN_PASSWORD not configured on server"}
        )

    try:
        body = await request.json()
        password = body.get("password", "")
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid request body"})

    if not hmac.compare_digest(password, admin_password):
        return JSONResponse(status_code=401, content={"error": "Invalid password"})

    token = _create_session()
    response = JSONResponse(content={"status": "ok"})
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,  # 24 hours
    )
    return response


@router.post("/admin/logout")
async def admin_logout(request: Request):
    """Clear the session cookie."""
    token = request.cookies.get("admin_session")
    if token:
        with _session_lock:
            _valid_sessions.discard(token)
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_session")
    return response


# ── Dashboard page ──────────────────────────────────────────────────

@router.get("/admin/crons")
async def admin_dashboard(request: Request):
    """Serve the cron monitoring dashboard."""
    if not _check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "public", "admin", "crons.html")
    if os.path.isfile(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=500)


# ── API endpoints (all require auth) ───────────────────────────────

@router.get("/admin/api/jobs")
async def admin_api_jobs(request: Request):
    """Return all jobs with their schedule, last run, next run, and status."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    scheduler_status = get_scheduler_status()
    running = get_running_jobs()
    last_runs = get_last_runs()

    # Build a rich job list
    jobs = []
    for job_info in scheduler_status["jobs"]:
        job_id = job_info["id"]
        # Determine shelter group from job_id
        parts = job_id.split("_")
        if len(parts) >= 2 and parts[-1] in ("inventory", "profiles", "all"):
            shelter = "_".join(parts[:-1])
            job_type = parts[-1]
        else:
            shelter = "system"
            job_type = job_id

        # Parse cron expression from trigger string
        trigger_str = job_info.get("trigger", "")

        # Running state
        is_running = job_id in running
        running_info = running.get(job_id, {})
        last_run = last_runs.get(job_id, {})

        jobs.append({
            "id": job_id,
            "shelter": shelter,
            "type": job_type,
            "trigger": trigger_str,
            "next_run": job_info.get("next_run"),
            "is_running": is_running,
            "running_since": running_info.get("started_at") if is_running else None,
            "last_run": last_run.get("finished_at") if last_run else None,
            "last_status": last_run.get("status") if last_run else None,
            "last_duration_s": last_run.get("duration_s") if last_run else None,
            "last_error": last_run.get("error") if last_run else None,
            "last_triggered_by": last_run.get("triggered_by") if last_run else None,
        })

    return JSONResponse(content={
        "scheduler_running": scheduler_status["running"],
        "total_jobs": len(jobs),
        "uptime_seconds": round((datetime.now(timezone.utc) - _SERVER_START_TIME).total_seconds()),
        "server_start": _SERVER_START_TIME.isoformat(),
        "jobs": sorted(jobs, key=lambda j: (j["shelter"], j["type"])),
    })


@router.get("/admin/api/jobs/{job_id}/history")
async def admin_api_job_history(job_id: str, request: Request):
    """Return the last 20 runs for a specific job from Supabase."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    if job_id not in JOB_REGISTRY:
        return JSONResponse(status_code=404, content={"error": f"Unknown job: {job_id}"})

    try:
        from jobs.lib.db import get_supabase_client
        client = get_supabase_client()
        result = (
            client.table("scrape_runs")
            .select("*")
            .eq("job_id", job_id)
            .order("started_at", desc=True)
            .limit(20)
            .execute()
        )
        runs = result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch history for {job_id}: {e}")
        runs = []

    return JSONResponse(content={"job_id": job_id, "runs": runs})


@router.post("/admin/api/jobs/{job_id}/run")
async def admin_api_trigger_job(job_id: str, request: Request):
    """Manually trigger a job. Runs in a background thread."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    if job_id not in JOB_REGISTRY:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown job: {job_id}"}
        )

    # Check if already running
    running = get_running_jobs()
    if job_id in running:
        return JSONResponse(
            status_code=409,
            content={"error": f"Job '{job_id}' is already running."}
        )

    def _run():
        try:
            logger.info(f"[admin] Manually triggered job: {job_id}")
            run_job_by_id(job_id, triggered_by="manual")
            logger.info(f"[admin] Manual job {job_id} completed successfully.")
        except Exception as e:
            logger.error(f"[admin] Manual job {job_id} failed: {e}")

    thread = threading.Thread(target=_run, name=f"admin-manual-{job_id}", daemon=True)
    thread.start()

    return JSONResponse(content={
        "status": "triggered",
        "job_id": job_id,
        "message": f"Job '{job_id}' started. Refresh to see progress.",
    })


@router.get("/admin/api/health")
async def admin_api_health(request: Request):
    """System health overview."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    uptime = (datetime.now(timezone.utc) - _SERVER_START_TIME).total_seconds()
    running = get_running_jobs()
    last_runs = get_last_runs()

    # Count recent failures (from in-memory state)
    recent_failures = sum(1 for r in last_runs.values() if r.get("status") == "failed")

    return JSONResponse(content={
        "status": "healthy",
        "uptime_seconds": round(uptime),
        "uptime_human": _format_duration(uptime),
        "server_start": _SERVER_START_TIME.isoformat(),
        "scheduler_running": scheduler.running,
        "total_registered_jobs": len(JOB_REGISTRY),
        "currently_running": len(running),
        "running_job_ids": list(running.keys()),
        "recent_failures": recent_failures,
    })


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    seconds = int(seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"
