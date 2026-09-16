"""
Admin dashboard routes for cron job monitoring and data quality monitors.

Provides a password-protected web dashboard at /admin for:
- /admin/crons  — Viewing all cron jobs with schedules, statuses, run history
- /admin/monitors — Toggling and running data quality monitors
- Manually triggering jobs and monitors
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


# ── Dashboard pages ─────────────────────────────────────────────────

@router.get("/admin")
async def admin_root(request: Request):
    """Redirect /admin to /admin/crons."""
    return RedirectResponse(url="/admin/crons", status_code=303)


@router.get("/admin/crons")
async def admin_dashboard(request: Request):
    """Serve the cron monitoring dashboard."""
    if not _check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "public", "admin", "crons.html")
    if os.path.isfile(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=500)


@router.get("/admin/monitors")
async def admin_monitors_page(request: Request):
    """Serve the data quality monitors dashboard."""
    if not _check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    monitors_path = os.path.join(os.path.dirname(__file__), "..", "public", "admin", "monitors.html")
    if os.path.isfile(monitors_path):
        return FileResponse(monitors_path, media_type="text/html")
    return HTMLResponse("<h1>Monitors page not found</h1>", status_code=500)


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


# ── Monitor API endpoints ───────────────────────────────────────────

@router.get("/admin/api/monitors")
async def admin_api_monitors(request: Request):
    """Return all monitors with their enabled state and last results."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    from monitors import get_monitor_config
    config = get_monitor_config()
    return JSONResponse(content={"monitors": list(config.values())})


@router.post("/admin/api/monitors/{monitor_id}/toggle")
async def admin_api_toggle_monitor(monitor_id: str, request: Request):
    """Toggle a monitor on/off."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    try:
        body = await request.json()
        enabled = body.get("enabled", True)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid request body"})

    from monitors import set_monitor_enabled
    if not set_monitor_enabled(monitor_id, enabled):
        return JSONResponse(status_code=404, content={"error": f"Unknown monitor: {monitor_id}"})

    return JSONResponse(content={"status": "ok", "monitor_id": monitor_id, "enabled": enabled})


@router.post("/admin/api/monitors/{monitor_id}/run")
async def admin_api_run_monitor(monitor_id: str, request: Request):
    """Manually trigger a single monitor."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    from monitors import run_monitor

    def _run():
        try:
            logger.info(f"[admin] Manually triggered monitor: {monitor_id}")
            run_monitor(monitor_id)
        except Exception as e:
            logger.error(f"[admin] Monitor {monitor_id} failed: {e}")

    thread = threading.Thread(target=_run, name=f"admin-monitor-{monitor_id}", daemon=True)
    thread.start()

    return JSONResponse(content={"status": "triggered", "monitor_id": monitor_id})


@router.post("/admin/api/monitors/run-all")
async def admin_api_run_all_monitors(request: Request):
    """Manually trigger all enabled monitors."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    from monitors import run_all_monitors

    def _run():
        try:
            logger.info("[admin] Manually triggered all monitors")
            run_all_monitors()
        except Exception as e:
            logger.error(f"[admin] Monitor sweep failed: {e}")

    thread = threading.Thread(target=_run, name="admin-monitors-all", daemon=True)
    thread.start()

    return JSONResponse(content={"status": "triggered", "message": "All enabled monitors started."})


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


# ── Backfill ────────────────────────────────────────────────────────

# In-memory store for backfill runs
_backfill_runs: dict = {}
_backfill_lock = threading.Lock()

# Shelter → scheduler job ID mapping
SHELTER_INVENTORY_JOBS = {
    "PACC": "pacc_inventory",
    "HSSA": "hssa_inventory",
    "MCACC": "mcacc_inventory",
    "DPA": "dpa_inventory",
    "PAWSCH": "pawsch_inventory",
    "MP": "mp_all",
    "WWLA": "wwla_all",
    "NYCACC": "nycacc_inventory",
    "NHS": "nhs_inventory",
    "EHR": "ehr_inventory",
    "MV": "mv_inventory",
    "RDR": "rdr_inventory",
    "RCHS": "rchs_inventory",
    "PHP": "php_inventory",
    "HHS": "hhs_inventory",
    "SAPA": "sapa_inventory",
}

SHELTER_PROFILES_JOBS = {
    "PACC": "pacc_profiles",
    "HSSA": "hssa_profiles",
    "MCACC": "mcacc_profiles",
    "DPA": "dpa_profiles",
    "PAWSCH": "pawsch_profiles",
    "MP": "mp_all",
    "WWLA": "wwla_all",
    "NYCACC": "nycacc_profiles",
    "NHS": "nhs_profiles",
    "EHR": "ehr_profiles",
    "MV": "mv_profiles",
    "RDR": "rdr_profiles",
    "RCHS": "rchs_profiles",
    "PHP": "php_profiles",
    "HHS": "hhs_profiles",
    "SAPA": "sapa_profiles",
}


@router.get("/admin/backfill")
async def admin_backfill_page(request: Request):
    """Serve the backfill dashboard page."""
    if not _check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    backfill_path = os.path.join(os.path.dirname(__file__), "..", "public", "admin", "backfill.html")
    if os.path.isfile(backfill_path):
        return FileResponse(backfill_path, media_type="text/html")
    return HTMLResponse("<h1>Backfill page not found</h1>", status_code=500)


@router.get("/admin/api/backfill/shelters")
async def admin_api_backfill_shelters(request: Request):
    """Return the list of shelters for the backfill UI."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    from jobs.lib.db import get_supabase_client
    try:
        sb = get_supabase_client()
        res = sb.table("shelters").select("shelter_id, shelter_name, location_display_name, relative_path").execute()
        shelters = sorted(res.data, key=lambda x: x.get("shelter_name", ""))
        return JSONResponse(content={"shelters": shelters})
    except Exception as e:
        logger.error(f"[backfill] Failed to fetch shelters: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/admin/api/backfill/start")
async def admin_api_backfill_start(request: Request):
    """Start a backfill run with the given configuration."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    body = await request.json()
    steps = body.get("steps", [])
    shelter_ids = body.get("shelters", [])
    dog_selection = body.get("dog_selection", {"mode": "all"})

    if not steps:
        return JSONResponse(status_code=400, content={"error": "No steps selected"})
    if not shelter_ids:
        return JSONResponse(status_code=400, content={"error": "No shelters selected"})

    # Check if a backfill is already running
    with _backfill_lock:
        for rid, run in _backfill_runs.items():
            if run.get("status") == "running":
                return JSONResponse(status_code=409, content={
                    "error": f"A backfill is already running (run_id: {rid})"
                })

    run_id = secrets.token_hex(6)

    # Resolve "ALL" to all shelter IDs
    if "ALL" in shelter_ids:
        all_sids = set(SHELTER_INVENTORY_JOBS.keys()) | set(SHELTER_PROFILES_JOBS.keys())
        shelter_ids = sorted(all_sids)

    run_state = {
        "run_id": run_id,
        "status": "running",
        "current_step": None,
        "steps": {s: {"status": "pending"} for s in steps},
        "config": {
            "steps": steps,
            "shelters": shelter_ids,
            "dog_selection": dog_selection,
        },
        "refreshed_dogs": [],
        "log": [],
        "abort": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    with _backfill_lock:
        _backfill_runs[run_id] = run_state

    def _execute():
        try:
            _run_backfill(run_id)
        except Exception as e:
            logger.error(f"[backfill] Run {run_id} crashed: {e}")
            with _backfill_lock:
                run = _backfill_runs.get(run_id, {})
                run["status"] = "error"
                run["error"] = str(e)
                _log(run_id, f"❌ Fatal error: {e}")

    thread = threading.Thread(target=_execute, name=f"backfill-{run_id}", daemon=True)
    thread.start()

    return JSONResponse(content={"run_id": run_id, "status": "started"})


@router.get("/admin/api/backfill/status/{run_id}")
async def admin_api_backfill_status(run_id: str, request: Request):
    """Return the current progress of a backfill run."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    with _backfill_lock:
        run = _backfill_runs.get(run_id)

    if not run:
        return JSONResponse(status_code=404, content={"error": f"Run {run_id} not found"})

    return JSONResponse(content={
        "run_id": run["run_id"],
        "status": run["status"],
        "current_step": run.get("current_step"),
        "steps": run.get("steps", {}),
        "refreshed_dogs": run.get("refreshed_dogs", []),
        "log": run.get("log", [])[-100:],  # Last 100 lines
        "error": run.get("error"),
    })


@router.post("/admin/api/backfill/abort/{run_id}")
async def admin_api_backfill_abort(run_id: str, request: Request):
    """Request abortion of a running backfill."""
    if not _check_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    with _backfill_lock:
        run = _backfill_runs.get(run_id)
        if not run:
            return JSONResponse(status_code=404, content={"error": f"Run {run_id} not found"})
        run["abort"] = True

    return JSONResponse(content={"status": "abort_requested"})


def _log(run_id: str, msg: str):
    """Append a log line to the run's log."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with _backfill_lock:
        run = _backfill_runs.get(run_id)
        if run:
            run["log"].append(f"[{ts}] {msg}")
    logger.info(f"[backfill:{run_id}] {msg}")


def _is_aborted(run_id: str) -> bool:
    with _backfill_lock:
        run = _backfill_runs.get(run_id)
        return run.get("abort", False) if run else True


def _update_step(run_id: str, step: str, **kwargs):
    with _backfill_lock:
        run = _backfill_runs.get(run_id)
        if run and step in run["steps"]:
            run["steps"][step].update(kwargs)


def _run_backfill(run_id: str):
    """Execute the backfill pipeline in sequence."""
    with _backfill_lock:
        run = _backfill_runs.get(run_id)
        if not run:
            return
        config = run["config"]
        steps = config["steps"]
        shelter_ids = config["shelters"]
        dog_selection = config["dog_selection"]

    for step in steps:
        if _is_aborted(run_id):
            _log(run_id, "⛔ Abort flag detected, stopping.")
            # Mark remaining steps as aborted
            with _backfill_lock:
                run = _backfill_runs.get(run_id)
                if run:
                    run["status"] = "aborted"
                    for s in steps:
                        if run["steps"].get(s, {}).get("status") == "pending":
                            run["steps"][s] = {"status": "aborted"}
            return

        with _backfill_lock:
            _backfill_runs[run_id]["current_step"] = step

        _log(run_id, f"▶ Starting step: {step}")

        try:
            if step == "cleanup":
                _run_backfill_cleanup(run_id)
            elif step == "inventory":
                _run_backfill_inventory(run_id, shelter_ids)
            elif step == "profiles":
                _run_backfill_profiles(run_id, shelter_ids)
            elif step == "facts":
                _run_backfill_facts(run_id, shelter_ids, dog_selection)
            elif step == "prompts":
                _run_backfill_prompts(run_id)
            else:
                _update_step(run_id, step, status="skipped", message=f"Unknown step: {step}")
                _log(run_id, f"⏭️ Skipped unknown step: {step}")
                continue

            if not _is_aborted(run_id):
                _update_step(run_id, step, status="done")
                _log(run_id, f"✅ Completed step: {step}")

        except Exception as e:
            _update_step(run_id, step, status="error", message=str(e)[:200])
            _log(run_id, f"❌ Step {step} failed: {e}")
            logger.exception(f"[backfill:{run_id}] Step {step} failed")

    # Done
    if not _is_aborted(run_id):
        with _backfill_lock:
            _backfill_runs[run_id]["status"] = "done"
        _log(run_id, "🎉 Backfill complete!")


def _run_backfill_cleanup(run_id: str):
    """Run the cleanup job (remove stale records)."""
    _update_step(run_id, "cleanup", status="running", message="Running cleanup cron...")
    try:
        run_job_by_id("cleanup_inactive_dogs", triggered_by="backfill")
        _update_step(run_id, "cleanup", message="Cleanup finished")
    except Exception as e:
        raise RuntimeError(f"Cleanup failed: {e}") from e


def _run_backfill_inventory(run_id: str, shelter_ids: list):
    """Run inventory scrape for each selected shelter."""
    # Filter to shelters that have inventory jobs
    actionable = [(sid, SHELTER_INVENTORY_JOBS[sid]) for sid in shelter_ids if sid in SHELTER_INVENTORY_JOBS]
    total = len(actionable)
    _update_step(run_id, "inventory", status="running", progress=0, total=total, message="Starting...")

    for i, (sid, job_id) in enumerate(actionable):
        if _is_aborted(run_id):
            _update_step(run_id, "inventory", status="aborted", progress=i, total=total)
            return

        _update_step(run_id, "inventory", progress=i, total=total, message=f"Processing {sid}...")
        _log(run_id, f"  📦 Inventory: {sid} ({i+1}/{total})")

        try:
            run_job_by_id(job_id, triggered_by="backfill")
        except Exception as e:
            _log(run_id, f"  ⚠️ Inventory {sid} failed: {e}")

    _update_step(run_id, "inventory", progress=total, total=total, message="All shelters done")


def _run_backfill_profiles(run_id: str, shelter_ids: list):
    """Run profile scrape for each selected shelter."""
    actionable = [(sid, SHELTER_PROFILES_JOBS[sid]) for sid in shelter_ids if sid in SHELTER_PROFILES_JOBS]
    # Dedupe job IDs (mp_all and wwla_all serve both inventory and profiles)
    seen_jobs = set()
    deduped = []
    for sid, job_id in actionable:
        if job_id not in seen_jobs:
            seen_jobs.add(job_id)
            deduped.append((sid, job_id))

    total = len(deduped)
    _update_step(run_id, "profiles", status="running", progress=0, total=total, message="Starting...")

    for i, (sid, job_id) in enumerate(deduped):
        if _is_aborted(run_id):
            _update_step(run_id, "profiles", status="aborted", progress=i, total=total)
            return

        _update_step(run_id, "profiles", progress=i, total=total, message=f"Processing {sid}...")
        _log(run_id, f"  📋 Profiles: {sid} ({i+1}/{total})")

        try:
            run_job_by_id(job_id, triggered_by="backfill")
        except Exception as e:
            _log(run_id, f"  ⚠️ Profiles {sid} failed: {e}")

    _update_step(run_id, "profiles", progress=total, total=total, message="All shelters done")


def _run_backfill_facts(run_id: str, shelter_ids: list, dog_selection: dict):
    """Run fact/persona/prompt pipeline for dogs matching the shelter & selection filters.

    Unlike the standard generate_prompts job, this:
    - Only processes dogs from the selected shelters
    - Respects the dog selection mode (all / random N / specific IDs)
    - Force-refreshes every selected dog regardless of last update time
    """
    import random as _random

    mode = dog_selection.get("mode", "all")
    _update_step(run_id, "facts", status="running", message="Building target list...")
    _log(run_id, f"  🧠 Fact tables: mode={mode}, shelters={shelter_ids}")

    try:
        import os, sys, time
        from jobs.lib.db import get_supabase_client
        from openai import OpenAI

        sb = get_supabase_client()
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Ensure pipeline modules are importable
        api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api")
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)

        from pipeline.extract_fact_profiles import extract_fact_profile
        from pipeline.build_persona_profiles import build_persona_profile
        from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

        # ── 1. Build target dog list ────────────────────────────────
        if mode == "specific":
            # User provided explicit animal IDs — use them directly
            target_ids = dog_selection.get("animal_ids", [])
            _log(run_id, f"  🧠 Specific IDs: {len(target_ids)} dogs")
        else:
            # Fetch active dogs filtered by selected shelters
            active_data = []
            offset = 0
            while True:
                res = sb.table("active_dogs").select("animal_id, shelter_id").range(offset, offset + 999).execute()
                active_data.extend(res.data)
                if len(res.data) < 1000:
                    break
                offset += 1000

            # Filter to selected shelters
            shelter_set = set(s.upper() for s in shelter_ids)
            shelter_dogs = {}  # shelter_id → [animal_ids]
            for row in active_data:
                sid = (row.get("shelter_id") or "").upper()
                if sid in shelter_set:
                    shelter_dogs.setdefault(sid, []).append(row["animal_id"])

            _log(run_id, f"  🧠 Active dogs in selected shelters: {sum(len(v) for v in shelter_dogs.values())}")

            if mode == "random":
                count = dog_selection.get("count", 5)
                target_ids = []
                for sid in sorted(shelter_dogs.keys()):
                    dogs = shelter_dogs[sid]
                    sample = _random.sample(dogs, min(count, len(dogs)))
                    target_ids.extend(sample)
                    _log(run_id, f"    {sid}: picked {len(sample)}/{len(dogs)} random dogs")
            else:
                # mode == "all"
                target_ids = []
                for sid in sorted(shelter_dogs.keys()):
                    target_ids.extend(shelter_dogs[sid])

        if not target_ids:
            _update_step(run_id, "facts", status="done", message="No target dogs found")
            _log(run_id, "  🧠 No dogs to process")
            return

        total = len(target_ids)
        _update_step(run_id, "facts", progress=0, total=total, message=f"Processing 0/{total} dogs...")
        _log(run_id, f"  🧠 Target list: {total} dogs to process")

        # ── 2. Fetch archetypes + distribution for persona scoring ──
        archetypes_res = sb.table("persona_archetypes").select("*").eq("active", True).execute()
        archetypes = archetypes_res.data

        dist_data = []
        dist_offset = 0
        while True:
            dist_res = sb.table("animal_persona_profiles").select("primary_archetype_key").range(dist_offset, dist_offset + 999).execute()
            dist_data.extend(dist_res.data)
            if len(dist_res.data) < 1000:
                break
            dist_offset += 1000
        distribution = {}
        for row in dist_data:
            k = row.get("primary_archetype_key")
            if k:
                distribution[k] = distribution.get(k, 0) + 1

        # ── 3. Shelter → location path mapping for refreshed dogs links ──
        shelters_res = sb.table("shelters").select("shelter_id, relative_path").execute()
        shelter_path_map = {s["shelter_id"]: s.get("relative_path", "") for s in shelters_res.data}

        # Build animal_id → shelter_id lookup
        active_lookup = []
        for i in range(0, len(target_ids), 100):
            chunk = target_ids[i:i+100]
            res = sb.table("active_dogs").select("animal_id, shelter_id").in_("animal_id", chunk).execute()
            active_lookup.extend(res.data)
        dog_shelter_map = {r["animal_id"]: r.get("shelter_id", "") for r in active_lookup}

        # ── 4. Process each dog ─────────────────────────────────────
        processed = 0
        for idx, aid in enumerate(target_ids):
            if _is_aborted(run_id):
                _update_step(run_id, "facts", status="aborted", progress=processed, total=total)
                return

            _update_step(run_id, "facts", progress=idx, total=total,
                         message=f"Processing {aid} ({idx+1}/{total})...")

            # Fetch full animal record
            animal_res = sb.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
            if not animal_res.data:
                _log(run_id, f"    ⚠️ {aid}: not found in animals table, skipping")
                continue

            animal_record = animal_res.data[0]
            record_hash = animal_record.get("record_hash", "none")
            updated_at = animal_record.get("updated_at")
            adoption_url = animal_record.get("shelter_profile_url")
            shelter_name = animal_record.get("shelter_name")

            # Strip internal fields before sending to LLM
            for key in ["id", "record_hash", "created_at", "updated_at", "last_scrape_run_id"]:
                animal_record.pop(key, None)

            try:
                # 1. Fact Extraction
                fact_profile_obj = extract_fact_profile(openai_client, animal_record)
                fact_profile = fact_profile_obj.model_dump()
                fact_profile["animal_id"] = aid
                fact_profile["source_record_hash"] = record_hash
                fact_profile["schema_version"] = "fact_v1"
                fact_profile["extraction_model"] = "gpt-5.4-mini"
                fact_profile["extraction_params_jsonb"] = {"temperature": 0.2}
                fact_profile["info_refreshed_at"] = updated_at
                fact_profile["adoption_url"] = adoption_url
                fact_profile["shelter_name"] = shelter_name
                sb.table("animal_fact_profiles").upsert(fact_profile).execute()

                fact_profile["full_bio"] = animal_record.get("bio", "")

                # 2. Persona Scoring
                persona_profile = build_persona_profile(openai_client, fact_profile, archetypes, distribution)
                assigned_key = persona_profile.get("primary_archetype_key")
                if assigned_key:
                    distribution[assigned_key] = distribution.get(assigned_key, 0) + 1
                persona_profile["source_record_hash"] = record_hash

                db_persona = {
                    "animal_id": persona_profile.get("animal_id"),
                    "source_record_hash": persona_profile.get("source_record_hash"),
                    "primary_archetype_key": persona_profile.get("primary_archetype_key"),
                    "selection_reasoning": persona_profile.get("selection_reasoning"),
                }
                sb.table("animal_persona_profiles").upsert(db_persona).execute()

                # 3. Prompt Rendering
                system_prompt = render_system_prompt(fact_profile, persona_profile)
                validation = validate_system_prompt(system_prompt)

                prompt_record = {
                    "animal_id": aid,
                    "prompt_version": "v3",
                    "source_record_hash": record_hash,
                    "system_prompt": system_prompt,
                    "render_context_jsonb": {
                        "fact_profile_used": True,
                        "persona_profile_used": True,
                        "archetype": persona_profile.get("primary_archetype_key"),
                    },
                    "validation_results_jsonb": validation,
                    "is_active": True,
                }
                sb.table("system_prompts_v2").upsert(prompt_record).execute()

                processed += 1
                dog_name = fact_profile.get("dog_name", "")
                _log(run_id, f"    ✅ {aid} ({dog_name})")

                # Add to refreshed_dogs list
                shelter_id = dog_shelter_map.get(aid, "")
                loc_path = shelter_path_map.get(shelter_id, "")
                with _backfill_lock:
                    run = _backfill_runs.get(run_id)
                    if run:
                        run["refreshed_dogs"].append({
                            "animal_id": aid,
                            "name": dog_name,
                            "location_path": loc_path,
                        })

            except Exception as e:
                _log(run_id, f"    ❌ {aid} failed: {e}")

        _update_step(run_id, "facts", progress=processed, total=total,
                     message=f"{processed}/{total} dogs refreshed")
        _log(run_id, f"  🧠 Fact extraction done: {processed}/{total} dogs refreshed")

    except Exception as e:
        raise RuntimeError(f"Fact extraction failed: {e}") from e


def _run_backfill_prompts(run_id: str):
    """Verify suggested_prompts table is populated (read-only check)."""
    _update_step(run_id, "prompts", status="running", message="Verifying prompt templates...")
    _log(run_id, "  📝 Prompt templates: verifying DB table...")

    try:
        from jobs.lib.db import get_supabase_client
        sb = get_supabase_client()
        res = sb.table("suggested_prompts").select("category, prompt_text").execute()
        count = len(res.data) if res.data else 0
        _update_step(run_id, "prompts", message=f"Verified: {count} templates in DB")
        _log(run_id, f"  📝 Prompt templates: {count} templates in DB ✓")
    except Exception as e:
        raise RuntimeError(f"Prompt template check failed: {e}") from e


