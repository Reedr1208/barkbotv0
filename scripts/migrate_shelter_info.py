"""
Migration: shelter adoption-info columns for the `find_shelter_info` chat agent action.

Idempotent — safe to re-run:
  1. Adds nullable columns on `public.shelters`:
       website_url text                      — official homepage
       process_details jsonb                 — daily adoption info pack
       process_details_updated_at timestamptz
  2. Fills website_url for every known shelter (only where it is NULL/empty, unless --force).

process_details is written by the daily job jobs/shelter_process_details_job.py,
which restricts its web search to the domain of website_url — so website_url
must be the shelter's OWN homepage, not a third-party listing host
(24petconnect, shelterluv, adoptapet, petango …).

When onboarding a new shelter, add its homepage to SHELTER_WEBSITES below and
re-run, or set it directly on the `shelters` row.

Usage:
    python scripts/migrate_shelter_info.py           # add columns + fill blank websites
    python scripts/migrate_shelter_info.py --force   # overwrite existing website values
"""

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jobs.lib.db import load_env  # noqa: E402

import psycopg2  # noqa: E402

SHELTER_WEBSITES = {
    "DGS": "https://doggoneseattle.org/",
    "DPA": "https://dallaspetsalive.org/",
    "EHR": "https://ehrdogs.org/",
    "HHS": "https://www.houstonhumane.org/",
    "HSSA": "https://hssaz.org/",
    "MCACC": "https://www.maricopa.gov/5268/Animal-Care-and-Control",
    "MP": "https://www.muddypawsrescue.org/",
    "MV": "https://muttville.org/",
    "NHS": "https://nassauhumane.org/",
    "NYCACC": "https://www.nycacc.org/",
    "PACC": "https://www.pima.gov/pima-animal-care-center-pacc",
    "PAWSCH": "https://www.pawschicago.org/",
    "PAWSCO": "https://pawsco.org/",
    "PHP": "https://phillypaws.org/",
    "RCHS": "https://rchumanesociety.org/",
    "RDR": "https://www.rocketdogrescue.org/",
    "SAPA": "https://sanantoniopetsalive.org/",
    "WWLA": "https://www.wagsandwalks.org/",
}


def _admin_conn():
    load_env()
    url = os.environ.get("storage_POSTGRES_URL_NON_POOLING") or os.environ.get("STORAGE_POSTGRES_URL_NON_POOLING")
    if not url:
        sys.exit("Missing storage_POSTGRES_URL_NON_POOLING in env/.env.local")
    url = re.sub(r"[?&]supa=[^&]*", "", url)
    return psycopg2.connect(url)


def main():
    force = "--force" in sys.argv
    conn = _admin_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE public.shelters ADD COLUMN IF NOT EXISTS website_url text")
        cur.execute("ALTER TABLE public.shelters ADD COLUMN IF NOT EXISTS process_details jsonb")
        cur.execute("ALTER TABLE public.shelters ADD COLUMN IF NOT EXISTS process_details_updated_at timestamptz")
        for shelter_id, url in SHELTER_WEBSITES.items():
            if force:
                cur.execute("UPDATE public.shelters SET website_url = %s WHERE shelter_id = %s", (url, shelter_id))
            else:
                cur.execute(
                    "UPDATE public.shelters SET website_url = %s "
                    "WHERE shelter_id = %s AND COALESCE(website_url, '') = ''",
                    (url, shelter_id),
                )
        # PostgREST caches the schema; ask it to reload so the new column is selectable immediately.
        cur.execute("NOTIFY pgrst, 'reload schema'")
        cur.execute("SELECT shelter_id, website_url FROM public.shelters ORDER BY shelter_id")
        rows = cur.fetchall()
    conn.close()
    missing = [sid for sid, url in rows if not url]
    for sid, url in rows:
        print(f"{sid:8} {url or '— MISSING —'}")
    if missing:
        print(f"\n⚠️  No website_url for: {', '.join(missing)} — add them to SHELTER_WEBSITES.")


if __name__ == "__main__":
    main()
