"""
Shelter job registry — single source of truth for all shelter scraper jobs.

Each entry maps a job_id to its module path, callable, and cron schedule.
The generic `run_shelter_job()` replaces the 30 individual wrapper functions
that previously lived in scheduler.py.
"""

import importlib
import logging
import sys
from contextlib import contextmanager

logger = logging.getLogger("barkbot.jobs.registry")


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


# ─── Registry ────────────────────────────────────────────────────────
# Each entry: {
#   "job_id":  unique identifier (used by scheduler + admin dashboard),
#   "module":  dotted module path to import,
#   "call":    how to invoke — either a function name or a custom callable key,
#   "cron":    5-field cron expression,
# }
#
# "call" values:
#   "main"              → module.main()
#   "scrape_inventory"  → module.scrape_inventory()
#   "pacc_inventory"    → custom: scrape_all_dogs() + save_to_supabase()
#   "mp_all"            → custom: fetch_dogs() + save_to_supabase()
#   "wwla_all"          → custom: fetch_html() + parse_records() + save_to_supabase()
# ──────────────────────────────────────────────────────────────────────

SHELTER_JOBS = [
    # ── PACC ──
    {"job_id": "pacc_inventory",   "module": "jobs.shelters.pacc.inventory",   "call": "pacc_inventory",   "cron": "0 8 * * *"},
    {"job_id": "pacc_profiles",    "module": "jobs.shelters.pacc.profiles",    "call": "main",             "cron": "5 * * * *"},

    # ── PAWSCH ──
    {"job_id": "pawsch_inventory", "module": "jobs.shelters.pawsch.inventory", "call": "main",             "cron": "0 */4 * * *"},
    {"job_id": "pawsch_profiles",  "module": "jobs.shelters.pawsch.profiles",  "call": "main",             "cron": "20 * * * *"},

    # ── MCACC ──
    {"job_id": "mcacc_inventory",  "module": "jobs.shelters.mcacc.inventory",  "call": "main",             "cron": "15 */4 * * *"},
    {"job_id": "mcacc_profiles",   "module": "jobs.shelters.mcacc.profiles",   "call": "main",             "cron": "50 * * * *"},

    # ── RCHS ──
    {"job_id": "rchs_inventory",   "module": "jobs.shelters.rchs.inventory",   "call": "scrape_inventory", "cron": "30 */4 * * *"},
    {"job_id": "rchs_profiles",    "module": "jobs.shelters.rchs.profiles",    "call": "main",             "cron": "10 * * * *"},

    # ── DPA ──
    {"job_id": "dpa_inventory",    "module": "jobs.shelters.dpa.inventory",    "call": "scrape_inventory", "cron": "40 */4 * * *"},
    {"job_id": "dpa_profiles",     "module": "jobs.shelters.dpa.profiles",     "call": "main",             "cron": "25 * * * *"},

    # ── NHS ──
    {"job_id": "nhs_inventory",    "module": "jobs.shelters.nhs.inventory",    "call": "scrape_inventory", "cron": "45 */4 * * *"},
    {"job_id": "nhs_profiles",     "module": "jobs.shelters.nhs.profiles",     "call": "main",             "cron": "55 * * * *"},

    # ── EHR ──
    {"job_id": "ehr_inventory",    "module": "jobs.shelters.ehr.inventory",    "call": "scrape_inventory", "cron": "50 */4 * * *"},
    {"job_id": "ehr_profiles",     "module": "jobs.shelters.ehr.profiles",     "call": "main",             "cron": "35 * * * *"},

    # ── MV ──
    {"job_id": "mv_inventory",     "module": "jobs.shelters.mv.inventory",     "call": "scrape_inventory", "cron": "0 */4 * * *"},
    {"job_id": "mv_profiles",      "module": "jobs.shelters.mv.profiles",      "call": "main",             "cron": "45 * * * *"},

    # ── RDR ──
    {"job_id": "rdr_inventory",    "module": "jobs.shelters.rdr.inventory",    "call": "scrape_inventory", "cron": "5 */4 * * *"},
    {"job_id": "rdr_profiles",     "module": "jobs.shelters.rdr.profiles",     "call": "main",             "cron": "15 * * * *"},

    # ── DGS ──
    {"job_id": "dgs_inventory",    "module": "jobs.shelters.dgs.inventory",    "call": "scrape_inventory", "cron": "10 */4 * * *"},
    {"job_id": "dgs_profiles",     "module": "jobs.shelters.dgs.profiles",     "call": "main",             "cron": "40 * * * *"},

    # ── MP (MuddyPaws) — combined inventory+profiles ──
    {"job_id": "mp_all",           "module": "jobs.shelters.mp.all",           "call": "mp_all",           "cron": "0 */6 * * *"},

    # ── WWLA (Wags & Walks LA) — combined inventory+profiles ──
    {"job_id": "wwla_all",         "module": "jobs.shelters.wwla.all",         "call": "wwla_all",         "cron": "0 */4 * * *"},

    # ── PHP ──
    {"job_id": "php_inventory",    "module": "jobs.shelters.php.inventory",    "call": "main",             "cron": "30 */4 * * *"},
    {"job_id": "php_profiles",     "module": "jobs.shelters.php.profiles",     "call": "main",             "cron": "35 * * * *"},

    # ── HSSA ──
    {"job_id": "hssa_inventory",   "module": "jobs.shelters.hssa.inventory",   "call": "scrape_inventory", "cron": "30 */4 * * *"},
    {"job_id": "hssa_profiles",    "module": "jobs.shelters.hssa.profiles",    "call": "main",             "cron": "0 * * * *"},

    # ── HHS ──
    {"job_id": "hhs_inventory",    "module": "jobs.shelters.hhs.inventory",    "call": "main",             "cron": "15 */4 * * *"},
    {"job_id": "hhs_profiles",     "module": "jobs.shelters.hhs.profiles",     "call": "main",             "cron": "45 * * * *"},

    # ── NYCACC ──
    {"job_id": "nycacc_inventory", "module": "jobs.shelters.nycacc.inventory", "call": "main",             "cron": "0 */4 * * *"},
    {"job_id": "nycacc_profiles",  "module": "jobs.shelters.nycacc.profiles",  "call": "main",             "cron": "30 * * * *"},

    # ── SAPA ──
    {"job_id": "sapa_inventory",   "module": "jobs.shelters.sapa.inventory",   "call": "main",             "cron": "0 */4 * * *"},
    {"job_id": "sapa_profiles",    "module": "jobs.shelters.sapa.profiles",    "call": "main",             "cron": "15 * * * *"},
]

# Build a lookup dict for run_shelter_job and the scheduler
_JOBS_BY_ID = {entry["job_id"]: entry for entry in SHELTER_JOBS}


def run_shelter_job(job_id: str) -> None:
    """
    Generic runner — imports the module and calls the appropriate entry point.
    Handles all shelter jobs regardless of their specific call convention.
    """
    entry = _JOBS_BY_ID.get(job_id)
    if not entry:
        raise ValueError(f"Unknown shelter job: {job_id}")

    mod = importlib.import_module(entry["module"])
    call = entry["call"]

    with _clean_argv():
        if call == "main":
            mod.main()

        elif call == "scrape_inventory":
            mod.scrape_inventory()

        elif call == "pacc_inventory":
            dogs = mod.scrape_all_dogs()
            mod.save_to_supabase(dogs)
            logger.info(f"{job_id}: Wrote {len(dogs)} dogs.")

        elif call == "mp_all":
            dogs = mod.fetch_dogs()
            mod.save_to_supabase(dogs)
            logger.info(f"{job_id}: Wrote {len(dogs)} dogs.")

        elif call == "wwla_all":
            html = mod.fetch_html(mod.LISTING_URL)
            dogs = mod.parse_records(html)
            mod.save_to_supabase(dogs)
            logger.info(f"{job_id}: Wrote {len(dogs)} dogs.")

        else:
            # Fallback: treat `call` as a function name on the module
            func = getattr(mod, call)
            func()


def get_all_job_ids() -> list[str]:
    """Return all registered shelter job IDs."""
    return [entry["job_id"] for entry in SHELTER_JOBS]
