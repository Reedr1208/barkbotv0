"""
Daily job: refresh `shelters.process_details` — the official dog-adoption info
pack (fees, process, requirements, visiting, contact, policies, links) that the
chat `find_shelter_info` tool serves instantly.

One web-search research call per shelter per day (routes/shelter_info.py →
research_shelter, same model as the dog recommender). A failed or empty result
never overwrites a previously good pack.

Scheduled in scheduler.py (job id `shelter_process_details`); also runnable via
POST /api/cron/shelter_process_details or locally:

    python -m jobs.shelter_process_details_job                 # stale shelters only
    python -m jobs.shelter_process_details_job --force         # all shelters
    python -m jobs.shelter_process_details_job --force PACC MP # specific shelters
"""

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from openai import OpenAI

from jobs.lib.db import get_supabase_client, now_iso

logger = logging.getLogger("barkbot.jobs.shelter_process_details")

MAX_WORKERS = 4
# Skip shelters refreshed more recently than this (manual re-runs, redeploys).
MIN_REFRESH_HOURS = 20


def _is_fresh(row: dict) -> bool:
    ts = row.get("process_details_updated_at")
    if not ts or not (row.get("process_details") or {}).get("found"):
        return False
    try:
        updated = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - updated < timedelta(hours=MIN_REFRESH_HOURS)


def run(force: bool = False, shelter_ids: list[str] | None = None) -> dict:
    from routes.shelter_info import research_shelter

    sb = get_supabase_client()
    rows = sb.table("shelters").select("*").order("shelter_id").execute().data or []
    if shelter_ids:
        wanted = {s.upper() for s in shelter_ids}
        rows = [r for r in rows if r.get("shelter_id") in wanted]
    if rows and "process_details" not in rows[0]:
        raise RuntimeError("shelters.process_details column missing — run scripts/migrate_shelter_info.py")

    todo = [r for r in rows if force or not _is_fresh(r)]
    stats = {"shelters": len(rows), "skipped_fresh": len(rows) - len(todo), "updated": 0,
             "not_found": 0, "failed": 0, "missing_website": []}
    if not todo:
        logger.info(f"shelter_process_details: nothing to do {json.dumps(stats)}")
        return stats

    client = OpenAI()
    t0 = time.time()

    def _one(row):
        if not row.get("website_url"):
            stats["missing_website"].append(row["shelter_id"])
        started = time.time()
        pack, meta = research_shelter(client, row)
        meta["secs"] = round(time.time() - started, 1)
        return row, pack, meta

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_one, r): r["shelter_id"] for r in todo}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                row, pack, meta = fut.result()
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"shelter_process_details: {sid} failed: {type(e).__name__}: {str(e)[:300]}")
                continue
            logger.info(f"shelter_process_details run: {json.dumps(meta, default=str)}")
            if not pack["found"]:
                # Keep any previous good pack; the chat tool will still link the official site.
                stats["not_found"] += 1
                continue
            sb.table("shelters").update({
                "process_details": pack,
                "process_details_updated_at": now_iso(),
            }).eq("shelter_id", sid).execute()
            stats["updated"] += 1

    stats["secs"] = round(time.time() - t0, 1)
    logger.info(f"shelter_process_details: done {json.dumps(stats)}")
    if stats["failed"] and not stats["updated"]:
        raise RuntimeError(f"All {stats['failed']} shelter research calls failed")
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    args = sys.argv[1:]
    print(json.dumps(run(force="--force" in args, shelter_ids=[a for a in args if not a.startswith("--")]),
                     indent=2))
