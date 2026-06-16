"""
Database and environment utilities shared across all BarkBot scraper jobs.

Consolidates the 3 different get_supabase_client() implementations and
the now_iso() / load_env() helpers that were copy-pasted in every job file.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from supabase import create_client


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def load_env() -> None:
    """
    Load environment variables from .env.local or .env.development.local
    if they exist.  Safe to call multiple times (idempotent).

    This unifies the 3 different env-loading patterns that existed across
    the codebase — some jobs loaded .env.local, some didn't, some stripped
    quotes and some didn't.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    for name in (".env.local", ".env.development.local"):
        env_file = project_root / name
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ[k] = v.strip().strip('"').strip("'")


def get_supabase_client():
    """
    Create and return a Supabase client using environment variables.

    Automatically calls load_env() first to ensure .env.local is loaded
    when running locally.
    """
    load_env()
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


def record_run_start(client, triggered_by: str, source_count: int = 0) -> int:
    """Insert a new scrape_runs row with status='running'. Returns the run ID."""
    payload = {
        "triggered_by": triggered_by,
        "source_count": source_count,
        "started_at": now_iso(),
        "status": "running",
    }
    row = client.table("scrape_runs").insert(payload).execute().data[0]
    return row["id"]


def record_run_finish(
    client,
    run_id: int,
    status: str,
    *,
    processed: int = 0,
    inserted: int = 0,
    updated: int = 0,
    unchanged: int = 0,
    errors: int = 0,
    notes: str | None = None,
) -> None:
    """Update an existing scrape_runs row with final status and counts."""
    payload = {
        "status": status,
        "processed_count": processed,
        "inserted_count": inserted,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "error_count": errors,
        "notes": notes,
        "finished_at": now_iso(),
    }
    client.table("scrape_runs").update(payload).eq("id", run_id).execute()
