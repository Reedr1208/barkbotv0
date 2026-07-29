"""
Data Quality & Cron Monitoring System for BarkBot.

Runs daily checks against the database and sends tailored ntfy notifications
for anomalies. Each monitor can be individually toggled on/off from the admin
console.

Monitors:
  1. stale_profiles     — Shelters with no profile update in 3+ days
  2. blank_bios         — Shelters where >25% of animals have empty bios
  3. missing_fact_profiles — Active animals missing LLM-generated fact profiles
  4. missing_system_prompts — Animals with fact profiles but no system prompt
  5. cron_failures      — Any cron jobs that failed in the last 24 hours
  6. empty_inventory    — Known shelters with 0 dogs in active_dogs
  7. stale_inventory    — Shelters whose inventory hasn't refreshed in 2+ days
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

import requests as http_requests

logger = logging.getLogger("barkbot.monitors")

# ── Known shelters (derived from scheduler job registry) ────────────
KNOWN_SHELTERS = [
    "PACC", "PAWSCH", "MCACC", "RCHS", "DPA", "NHS", "EHR",
    "MV", "RDR", "MP", "WWLA", "PHP", "HSSA", "HHS", "NYCACC", "SAPA",
]

# ── In-memory monitor state ─────────────────────────────────────────
_monitor_state: dict[str, dict] = {}
_state_lock = threading.Lock()


def _default_state() -> dict:
    """Return default state for all monitors."""
    return {mid: {"enabled": True, "last_run": None, "last_result": None}
            for mid in MONITOR_REGISTRY}


def get_monitor_config() -> dict[str, dict]:
    """Return current monitor config with enabled state and last results."""
    with _state_lock:
        if not _monitor_state:
            _monitor_state.update(_default_state())
        result = {}
        for mid, meta in MONITOR_REGISTRY.items():
            state = _monitor_state.get(mid, {"enabled": True, "last_run": None, "last_result": None})
            result[mid] = {
                "id": mid,
                "name": meta["name"],
                "description": meta["description"],
                "enabled": state.get("enabled", True),
                "last_run": state.get("last_run"),
                "last_result": state.get("last_result"),
            }
        return result


def set_monitor_enabled(monitor_id: str, enabled: bool) -> bool:
    """Toggle a monitor on/off. Returns True if the monitor exists."""
    if monitor_id not in MONITOR_REGISTRY:
        return False
    with _state_lock:
        if not _monitor_state:
            _monitor_state.update(_default_state())
        if monitor_id not in _monitor_state:
            _monitor_state[monitor_id] = {"enabled": True, "last_run": None, "last_result": None}
        _monitor_state[monitor_id]["enabled"] = enabled
    return True


def _record_result(monitor_id: str, result: dict):
    """Record the result of a monitor run."""
    with _state_lock:
        if monitor_id not in _monitor_state:
            _monitor_state[monitor_id] = {"enabled": True, "last_run": None, "last_result": None}
        _monitor_state[monitor_id]["last_run"] = datetime.now(timezone.utc).isoformat()
        _monitor_state[monitor_id]["last_result"] = result


# ── ntfy notification helper ────────────────────────────────────────

def _send_notification(title: str, body: str, tags: str = "warning", priority: str = "default"):
    """Send a notification via ntfy using the NFTY_TOPIC env var."""
    topic = os.environ.get("NFTY_TOPIC")
    if not topic:
        logger.warning("NFTY_TOPIC not set — skipping notification: %s", title)
        return
    try:
        http_requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": title,
                "Tags": tags,
                "Priority": priority,
            },
            timeout=10,
        )
        logger.info("Sent ntfy notification: %s", title)
    except Exception as e:
        logger.error("Failed to send ntfy notification: %s", e)


# ── Supabase helper ─────────────────────────────────────────────────

def _get_client():
    """Get a Supabase client (lazy import to avoid circular deps)."""
    from jobs.lib.db import get_supabase_client
    return get_supabase_client()


def _fetch_all_rows(query):
    """Paginate through a Supabase query to get all rows."""
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        res = query.range(offset, offset + page_size - 1).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows


# ═══════════════════════════════════════════════════════════════════
#  MONITOR IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════


def _check_stale_profiles() -> dict:
    """
    Monitor 1: Stale profile data
    Detects shelters where no `animals` record has been updated in 3+ days,
    suggesting the profiles scraper is silently failing or the site changed.
    """
    client = _get_client()
    threshold = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    findings = []

    for shelter_id in KNOWN_SHELTERS:
        try:
            res = (client.table("animals")
                   .select("updated_at")
                   .like("animal_id", f"{shelter_id}-%")
                   .order("updated_at", desc=True)
                   .limit(1)
                   .execute())
            if not res.data:
                continue  # No animals for this shelter — handled by empty_inventory
            last_update = res.data[0]["updated_at"]
            if last_update < threshold:
                days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last_update.replace("Z", "+00:00"))).days
                findings.append({"shelter": shelter_id, "last_update": last_update, "days_ago": days_ago})
        except Exception as e:
            logger.error("stale_profiles check failed for %s: %s", shelter_id, e)

    for f in findings:
        _send_notification(
            title=f"📋 Stale Profiles — {f['shelter']}",
            body=f"{f['shelter']} profiles haven't been updated in {f['days_ago']} days (last: {f['last_update'][:10]})",
            tags="warning,clipboard",
        )

    return {"findings_count": len(findings), "findings": findings}


def _check_blank_bios() -> dict:
    """
    Monitor 2: High blank bio ratio
    Detects shelters where >25% of active animals have NULL/empty bio,
    indicating the profiles scraper isn't populating bios.
    """
    client = _get_client()
    findings = []

    for shelter_id in KNOWN_SHELTERS:
        try:
            # Count total animals for this shelter
            total_res = (client.table("animals")
                         .select("animal_id", count="exact")
                         .like("animal_id", f"{shelter_id}-%")
                         .execute())
            total = total_res.count or 0
            if total == 0:
                continue

            # Count animals with blank bios
            blank_res = (client.table("animals")
                         .select("animal_id", count="exact")
                         .like("animal_id", f"{shelter_id}-%")
                         .or_("bio.is.null,bio.eq.")
                         .execute())
            blank = blank_res.count or 0

            ratio = blank / total if total > 0 else 0
            if ratio > 0.25 and blank >= 3:  # At least 3 blank to avoid noise from small shelters
                findings.append({
                    "shelter": shelter_id,
                    "blank": blank,
                    "total": total,
                    "pct": round(ratio * 100),
                })
        except Exception as e:
            logger.error("blank_bios check failed for %s: %s", shelter_id, e)

    for f in findings:
        _send_notification(
            title=f"📝 Blank Bios — {f['shelter']}",
            body=f"{f['shelter']} has {f['blank']}/{f['total']} animals ({f['pct']}%) with blank bios",
            tags="warning,memo",
        )

    return {"findings_count": len(findings), "findings": findings}


def _check_missing_fact_profiles() -> dict:
    """
    Monitor 3: Animals without fact profiles
    Detects active animals that exist in `animals` but have no corresponding
    `animal_fact_profiles` row, meaning the LLM pipeline hasn't processed them.
    """
    client = _get_client()

    # Get all active_dogs animal_ids
    active_rows = _fetch_all_rows(client.table("active_dogs").select("animal_id, shelter_id"))
    if not active_rows:
        return {"findings_count": 0, "findings": []}

    active_ids = {r["animal_id"] for r in active_rows}

    # Get all animal_fact_profiles animal_ids
    fact_rows = _fetch_all_rows(client.table("animal_fact_profiles").select("animal_id"))
    fact_ids = {r["animal_id"] for r in fact_rows}

    missing = active_ids - fact_ids

    # Group by shelter
    shelter_counts: dict[str, int] = {}
    for aid in missing:
        parts = aid.split("-", 1)
        sid = parts[0] if len(parts) > 1 else "UNKNOWN"
        shelter_counts[sid] = shelter_counts.get(sid, 0) + 1

    findings = [{"shelter": s, "missing_count": c} for s, c in sorted(shelter_counts.items()) if c > 0]

    if len(missing) > 0:
        # Send one consolidated notification
        lines = [f"  • {f['shelter']}: {f['missing_count']} dogs" for f in findings]
        _send_notification(
            title=f"🧩 Missing Fact Profiles — {len(missing)} total",
            body=f"{len(missing)} active dogs have no fact profile:\n" + "\n".join(lines),
            tags="warning,jigsaw",
        )

    return {"findings_count": len(missing), "findings": findings}


def _check_missing_system_prompts() -> dict:
    """
    Monitor 4: Animals without system prompts
    Detects animals that have a fact profile but no system_prompts_v2 row,
    so they can't participate in chat.
    """
    client = _get_client()

    fact_rows = _fetch_all_rows(client.table("animal_fact_profiles").select("animal_id"))
    fact_ids = {r["animal_id"] for r in fact_rows}

    prompt_rows = _fetch_all_rows(client.table("system_prompts_v2").select("animal_id"))
    prompt_ids = {r["animal_id"] for r in prompt_rows}

    missing = fact_ids - prompt_ids

    shelter_counts: dict[str, int] = {}
    for aid in missing:
        parts = aid.split("-", 1)
        sid = parts[0] if len(parts) > 1 else "UNKNOWN"
        shelter_counts[sid] = shelter_counts.get(sid, 0) + 1

    findings = [{"shelter": s, "missing_count": c} for s, c in sorted(shelter_counts.items()) if c > 0]

    if len(missing) > 0:
        lines = [f"  • {f['shelter']}: {f['missing_count']} dogs" for f in findings]
        _send_notification(
            title=f"💬 Missing System Prompts — {len(missing)} total",
            body=f"{len(missing)} dogs have fact profiles but no system prompt:\n" + "\n".join(lines),
            tags="warning,speech_balloon",
        )

    return {"findings_count": len(missing), "findings": findings}


def _check_cron_failures() -> dict:
    """
    Monitor 5: Recent cron job failures
    Checks scrape_runs for any jobs that failed in the last 24 hours.
    """
    client = _get_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    try:
        res = (client.table("scrape_runs")
               .select("job_id, status, notes, started_at")
               .eq("status", "failed")
               .gte("started_at", since)
               .order("started_at", desc=True)
               .limit(50)
               .execute())
        failures = res.data or []
    except Exception as e:
        logger.error("cron_failures check failed: %s", e)
        failures = []

    findings = []
    for f in failures:
        findings.append({
            "job_id": f.get("job_id", "unknown"),
            "started_at": f.get("started_at", ""),
            "notes": (f.get("notes") or "")[:200],
        })

    if findings:
        # Group by job_id
        job_counts: dict[str, int] = {}
        for f in findings:
            job_counts[f["job_id"]] = job_counts.get(f["job_id"], 0) + 1

        lines = [f"  • {jid}: {cnt}x" for jid, cnt in sorted(job_counts.items())]
        _send_notification(
            title=f"❌ Cron Failures — {len(findings)} in last 24h",
            body=f"{len(findings)} cron failures detected:\n" + "\n".join(lines),
            tags="rotating_light,x",
        )

    return {"findings_count": len(findings), "findings": findings}


def _check_empty_inventory() -> dict:
    """
    Monitor 6: Shelter with zero active dogs
    Detects known shelters that have 0 dogs in active_dogs, suggesting
    the inventory scraper broke or returned empty results.
    """
    client = _get_client()
    findings = []

    # Get counts per shelter_id
    all_active = _fetch_all_rows(client.table("active_dogs").select("shelter_id"))
    shelter_counts: dict[str, int] = {}
    for row in all_active:
        sid = row.get("shelter_id", "UNKNOWN")
        shelter_counts[sid] = shelter_counts.get(sid, 0) + 1

    for shelter_id in KNOWN_SHELTERS:
        count = shelter_counts.get(shelter_id, 0)
        if count == 0:
            findings.append({"shelter": shelter_id, "count": 0})

    for f in findings:
        _send_notification(
            title=f"🚨 Empty Inventory — {f['shelter']}",
            body=f"{f['shelter']} has 0 dogs in active inventory. The inventory scraper may have failed.",
            tags="rotating_light,warning",
            priority="high",
        )

    return {"findings_count": len(findings), "findings": findings}


def _check_stale_inventory() -> dict:
    """
    Monitor 7: Shelter inventory not refreshed
    Detects shelters where active_dogs.scraped_at hasn't been updated
    in 2+ days, indicating the inventory scraper is silently stale.
    """
    client = _get_client()
    threshold = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    findings = []

    for shelter_id in KNOWN_SHELTERS:
        try:
            res = (client.table("active_dogs")
                   .select("scraped_at")
                   .eq("shelter_id", shelter_id)
                   .order("scraped_at", desc=True)
                   .limit(1)
                   .execute())
            if not res.data:
                continue  # No inventory — handled by empty_inventory
            last_scraped = res.data[0].get("scraped_at")
            if last_scraped and last_scraped < threshold:
                days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last_scraped.replace("Z", "+00:00"))).days
                findings.append({"shelter": shelter_id, "last_scraped": last_scraped, "days_ago": days_ago})
        except Exception as e:
            logger.error("stale_inventory check failed for %s: %s", shelter_id, e)

    for f in findings:
        _send_notification(
            title=f"📦 Stale Inventory — {f['shelter']}",
            body=f"{f['shelter']} inventory hasn't been refreshed in {f['days_ago']} days (last: {f['last_scraped'][:10]})",
            tags="warning,package",
        )

    return {"findings_count": len(findings), "findings": findings}


# ═══════════════════════════════════════════════════════════════════
#  MONITOR REGISTRY
# ═══════════════════════════════════════════════════════════════════

MONITOR_REGISTRY: dict[str, dict[str, Any]] = {
    "stale_profiles": {
        "name": "Stale Profiles",
        "description": "Shelters with no profile update in 3+ days",
        "fn": _check_stale_profiles,
    },
    "blank_bios": {
        "name": "Blank Bios",
        "description": "Shelters where >25% of animals have empty bios",
        "fn": _check_blank_bios,
    },
    "missing_fact_profiles": {
        "name": "Missing Fact Profiles",
        "description": "Active dogs without LLM-generated fact profiles",
        "fn": _check_missing_fact_profiles,
    },
    "missing_system_prompts": {
        "name": "Missing System Prompts",
        "description": "Dogs with fact profiles but no chat prompt (can't chat)",
        "fn": _check_missing_system_prompts,
    },
    "cron_failures": {
        "name": "Cron Failures",
        "description": "Cron jobs that failed in the last 24 hours",
        "fn": _check_cron_failures,
    },
    "empty_inventory": {
        "name": "Empty Inventory",
        "description": "Known shelters with 0 dogs in active inventory",
        "fn": _check_empty_inventory,
    },
    "stale_inventory": {
        "name": "Stale Inventory",
        "description": "Shelters whose inventory hasn't refreshed in 2+ days",
        "fn": _check_stale_inventory,
    },
}


# ═══════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════

def run_monitor(monitor_id: str) -> dict | None:
    """Run a single monitor by ID. Returns the result dict or None if unknown."""
    meta = MONITOR_REGISTRY.get(monitor_id)
    if not meta:
        return None
    logger.info("Running monitor: %s", monitor_id)
    try:
        result = meta["fn"]()
        result["status"] = "ok"
    except Exception as e:
        logger.error("Monitor %s failed: %s", monitor_id, e)
        result = {"status": "error", "error": str(e), "findings_count": 0, "findings": []}
    _record_result(monitor_id, result)
    return result


def run_all_monitors() -> dict:
    """Run all enabled monitors. Returns a summary dict."""
    results = {}
    with _state_lock:
        if not _monitor_state:
            _monitor_state.update(_default_state())
        enabled_ids = [mid for mid, s in _monitor_state.items() if s.get("enabled", True)]

    for mid in enabled_ids:
        results[mid] = run_monitor(mid)

    total_findings = sum(r.get("findings_count", 0) for r in results.values() if r)
    logger.info("Monitor sweep complete: %d monitors ran, %d total findings", len(results), total_findings)
    return {
        "monitors_ran": len(results),
        "total_findings": total_findings,
        "results": results,
    }
