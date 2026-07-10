"""
APScheduler-based cron scheduler for BarkBot.

Unifies all 37 cron jobs that were previously split between Vercel crons (24)
and GitHub Actions (11) into a single in-process scheduler. Jobs call the
underlying Python functions directly — no subprocess spawning.
"""

import asyncio
import logging
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

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


def _job_listener(event):
    """Log job execution results."""
    if event.exception:
        logger.error(f"Job {event.job_id} failed: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} completed successfully.")


scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


# ──────────────────────────────────────────────────────────────────────
# Job wrapper functions
#
# Each wrapper calls the underlying shelter module function directly.
# This replaces both:
# - Vercel cron handlers (api/*.py) that spawned subprocesses
# - GitHub Actions workflows that checked out the repo and ran scripts
# ──────────────────────────────────────────────────────────────────────

def _run_pacc_inventory():
    from jobs.shelters.pacc.inventory import scrape_all_dogs, save_to_supabase
    dogs = scrape_all_dogs()
    save_to_supabase(dogs)
    logger.info(f"pacc_inventory: Wrote {len(dogs)} dogs.")


def _run_pacc_profiles():
    from jobs.shelters.pacc.profiles import main
    main()


def _run_ahscn_inventory():
    from jobs.shelters.ahscn.inventory import main
    main()


def _run_ahscn_profiles():
    from jobs.shelters.ahscn.profiles import main
    main()


def _run_pawsch_inventory():
    from jobs.shelters.pawsch.inventory import main
    main()


def _run_pawsch_profiles():
    from jobs.shelters.pawsch.profiles import main
    main()


def _run_mcacc_inventory():
    from jobs.shelters.mcacc.inventory import main
    main()


def _run_mcacc_profiles():
    from jobs.shelters.mcacc.profiles import main
    main()


def _run_rchs_inventory():
    from jobs.shelters.rchs.inventory import scrape_inventory
    scrape_inventory()


def _run_rchs_profiles():
    from jobs.shelters.rchs.profiles import main
    main()


def _run_dpa_inventory():
    from jobs.shelters.dpa.inventory import scrape_inventory
    scrape_inventory()


def _run_dpa_profiles():
    from jobs.shelters.dpa.profiles import main
    main()


def _run_nhs_inventory():
    from jobs.shelters.nhs.inventory import scrape_inventory
    scrape_inventory()


def _run_nhs_profiles():
    from jobs.shelters.nhs.profiles import main
    main()


def _run_ehr_inventory():
    from jobs.shelters.ehr.inventory import scrape_inventory
    scrape_inventory()


def _run_ehr_profiles():
    from jobs.shelters.ehr.profiles import main
    main()


def _run_mv_inventory():
    from jobs.shelters.mv.inventory import scrape_inventory
    scrape_inventory()


def _run_mv_profiles():
    from jobs.shelters.mv.profiles import main
    main()


def _run_rdr_inventory():
    from jobs.shelters.rdr.inventory import scrape_inventory
    scrape_inventory()


def _run_rdr_profiles():
    from jobs.shelters.rdr.profiles import main
    main()


def _run_mp_all():
    from jobs.shelters.mp.all import fetch_dogs, save_to_supabase
    dogs = fetch_dogs()
    save_to_supabase(dogs)
    logger.info(f"mp_all: Wrote {len(dogs)} dogs.")


def _run_wwla_all():
    from jobs.shelters.wwla.all import fetch_html, parse_records, save_to_supabase, LISTING_URL
    html = fetch_html(LISTING_URL)
    dogs = parse_records(html)
    save_to_supabase(dogs)
    logger.info(f"wwla_all: Wrote {len(dogs)} dogs.")


def _run_php_inventory():
    from jobs.shelters.php.inventory import main
    main()


def _run_php_profiles():
    from jobs.shelters.php.profiles import main
    main()


def _run_hssa_inventory():
    from jobs.shelters.hssa.inventory import scrape_inventory
    scrape_inventory()


def _run_hssa_profiles():
    from jobs.shelters.hssa.profiles import main
    main()


def _run_hhs_inventory():
    from jobs.shelters.hhs.inventory import main
    main()


def _run_hhs_profiles():
    from jobs.shelters.hhs.profiles import main
    with _clean_argv():
        main()


def _run_nycacc_inventory():
    from jobs.shelters.nycacc.inventory import main_async, build_arg_parser
    parsed_args = build_arg_parser().parse_args([])
    asyncio.run(main_async(parsed_args))


def _run_nycacc_profiles():
    from jobs.shelters.nycacc.profiles import main_async, build_arg_parser
    asyncio.run(main_async(build_arg_parser().parse_args([])))


def _run_sapa_inventory():
    from jobs.shelters.sapa.inventory import main
    main()


def _run_sapa_profiles():
    from jobs.shelters.sapa.profiles import main
    with _clean_argv():
        main()


def _run_generate_prompts():
    from jobs.generate_prompts_job import run
    run()


def _run_cleanup_inactive_dogs():
    from jobs import __path__ as jobs_path
    import importlib
    # Use importlib to avoid issues with the '08_' prefix
    spec = importlib.util.spec_from_file_location(
        "cleanup_inactive_dogs",
        __import__("os").path.join(__import__("os").path.dirname(__file__), "jobs", "08_cleanup_inactive_dogs.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


# ──────────────────────────────────────────────────────────────────────
# Registry: maps job_id → wrapper function
# Used by both the scheduler and the manual trigger endpoints
# ──────────────────────────────────────────────────────────────────────

JOB_REGISTRY = {
    "pacc_inventory": _run_pacc_inventory,
    "pacc_profiles": _run_pacc_profiles,
    "ahscn_inventory": _run_ahscn_inventory,
    "ahscn_profiles": _run_ahscn_profiles,
    "pawsch_inventory": _run_pawsch_inventory,
    "pawsch_profiles": _run_pawsch_profiles,
    "mcacc_inventory": _run_mcacc_inventory,
    "mcacc_profiles": _run_mcacc_profiles,
    "rchs_inventory": _run_rchs_inventory,
    "rchs_profiles": _run_rchs_profiles,
    "dpa_inventory": _run_dpa_inventory,
    "dpa_profiles": _run_dpa_profiles,
    "nhs_inventory": _run_nhs_inventory,
    "nhs_profiles": _run_nhs_profiles,
    "ehr_inventory": _run_ehr_inventory,
    "ehr_profiles": _run_ehr_profiles,
    "mv_inventory": _run_mv_inventory,
    "mv_profiles": _run_mv_profiles,
    "rdr_inventory": _run_rdr_inventory,
    "rdr_profiles": _run_rdr_profiles,
    "mp_all": _run_mp_all,
    "wwla_all": _run_wwla_all,
    "php_inventory": _run_php_inventory,
    "php_profiles": _run_php_profiles,
    "hssa_inventory": _run_hssa_inventory,
    "hssa_profiles": _run_hssa_profiles,
    "hhs_inventory": _run_hhs_inventory,
    "hhs_profiles": _run_hhs_profiles,
    "nycacc_inventory": _run_nycacc_inventory,
    "nycacc_profiles": _run_nycacc_profiles,
    "sapa_inventory": _run_sapa_inventory,
    "sapa_profiles": _run_sapa_profiles,
    "generate_prompts": _run_generate_prompts,
    "cleanup_inactive_dogs": _run_cleanup_inactive_dogs,
}


def run_job_by_id(job_id: str):
    """Run a job synchronously by its ID. Used by manual trigger endpoints."""
    func = JOB_REGISTRY.get(job_id)
    if not func:
        raise ValueError(f"Unknown job: {job_id}")
    func()


def setup_schedules():
    """Register all cron schedules with APScheduler."""

    # ── Vercel crons (previously in vercel.json) ──────────────────────

    # PACC
    scheduler.add_job(_run_pacc_inventory, CronTrigger.from_crontab("0 8 * * *"), id="pacc_inventory", replace_existing=True)
    scheduler.add_job(_run_pacc_profiles, CronTrigger.from_crontab("5 * * * *"), id="pacc_profiles", replace_existing=True)

    # AHSCN
    scheduler.add_job(_run_ahscn_inventory, CronTrigger.from_crontab("0 */4 * * *"), id="ahscn_inventory", replace_existing=True)
    scheduler.add_job(_run_ahscn_profiles, CronTrigger.from_crontab("45 * * * *"), id="ahscn_profiles", replace_existing=True)

    # PAWSCH
    scheduler.add_job(_run_pawsch_inventory, CronTrigger.from_crontab("0 */4 * * *"), id="pawsch_inventory", replace_existing=True)
    scheduler.add_job(_run_pawsch_profiles, CronTrigger.from_crontab("20 * * * *"), id="pawsch_profiles", replace_existing=True)

    # MCACC
    scheduler.add_job(_run_mcacc_inventory, CronTrigger.from_crontab("15 */4 * * *"), id="mcacc_inventory", replace_existing=True)
    scheduler.add_job(_run_mcacc_profiles, CronTrigger.from_crontab("50 * * * *"), id="mcacc_profiles", replace_existing=True)

    # RCHS
    scheduler.add_job(_run_rchs_inventory, CronTrigger.from_crontab("30 */4 * * *"), id="rchs_inventory", replace_existing=True)
    scheduler.add_job(_run_rchs_profiles, CronTrigger.from_crontab("10 * * * *"), id="rchs_profiles", replace_existing=True)

    # DPA
    scheduler.add_job(_run_dpa_inventory, CronTrigger.from_crontab("40 */4 * * *"), id="dpa_inventory", replace_existing=True)
    scheduler.add_job(_run_dpa_profiles, CronTrigger.from_crontab("25 * * * *"), id="dpa_profiles", replace_existing=True)

    # NHS
    scheduler.add_job(_run_nhs_inventory, CronTrigger.from_crontab("45 */4 * * *"), id="nhs_inventory", replace_existing=True)
    scheduler.add_job(_run_nhs_profiles, CronTrigger.from_crontab("55 * * * *"), id="nhs_profiles", replace_existing=True)

    # EHR
    scheduler.add_job(_run_ehr_inventory, CronTrigger.from_crontab("50 */4 * * *"), id="ehr_inventory", replace_existing=True)
    scheduler.add_job(_run_ehr_profiles, CronTrigger.from_crontab("35 * * * *"), id="ehr_profiles", replace_existing=True)

    # MV
    scheduler.add_job(_run_mv_inventory, CronTrigger.from_crontab("0 */4 * * *"), id="mv_inventory", replace_existing=True)
    scheduler.add_job(_run_mv_profiles, CronTrigger.from_crontab("45 * * * *"), id="mv_profiles", replace_existing=True)

    # RDR
    scheduler.add_job(_run_rdr_inventory, CronTrigger.from_crontab("5 */4 * * *"), id="rdr_inventory", replace_existing=True)
    scheduler.add_job(_run_rdr_profiles, CronTrigger.from_crontab("15 * * * *"), id="rdr_profiles", replace_existing=True)

    # MP (MuddyPaws)
    scheduler.add_job(_run_mp_all, CronTrigger.from_crontab("0 */6 * * *"), id="mp_all", replace_existing=True)

    # WWLA
    scheduler.add_job(_run_wwla_all, CronTrigger.from_crontab("0 */4 * * *"), id="wwla_all", replace_existing=True)

    # PHP (profiles only — inventory on GitHub Actions, now moved here)
    scheduler.add_job(_run_php_profiles, CronTrigger.from_crontab("35 * * * *"), id="php_profiles", replace_existing=True)

    # Generate prompts (pipeline)
    scheduler.add_job(_run_generate_prompts, CronTrigger.from_crontab("*/30 * * * *"), id="generate_prompts", replace_existing=True)

    # ── GitHub Actions crons (previously in .github/workflows/) ──────

    # HSSA (Playwright)
    scheduler.add_job(_run_hssa_inventory, CronTrigger.from_crontab("30 */4 * * *"), id="hssa_inventory", replace_existing=True)
    scheduler.add_job(_run_hssa_profiles, CronTrigger.from_crontab("0 * * * *"), id="hssa_profiles", replace_existing=True)

    # HHS (Playwright)
    scheduler.add_job(_run_hhs_inventory, CronTrigger.from_crontab("15 */4 * * *"), id="hhs_inventory", replace_existing=True)
    scheduler.add_job(_run_hhs_profiles, CronTrigger.from_crontab("45 * * * *"), id="hhs_profiles", replace_existing=True)

    # NYCACC (Playwright / async)
    scheduler.add_job(_run_nycacc_inventory, CronTrigger.from_crontab("0 */4 * * *"), id="nycacc_inventory", replace_existing=True)
    scheduler.add_job(_run_nycacc_profiles, CronTrigger.from_crontab("30 * * * *"), id="nycacc_profiles", replace_existing=True)

    # PHP inventory (Playwright — was GitHub Actions only)
    scheduler.add_job(_run_php_inventory, CronTrigger.from_crontab("30 */4 * * *"), id="php_inventory", replace_existing=True)

    # SAPA (Playwright)
    scheduler.add_job(_run_sapa_inventory, CronTrigger.from_crontab("0 */4 * * *"), id="sapa_inventory", replace_existing=True)
    scheduler.add_job(_run_sapa_profiles, CronTrigger.from_crontab("15 * * * *"), id="sapa_profiles", replace_existing=True)

    # Cleanup inactive dogs
    scheduler.add_job(_run_cleanup_inactive_dogs, CronTrigger.from_crontab("15 */4 * * *"), id="cleanup_inactive_dogs", replace_existing=True)

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
