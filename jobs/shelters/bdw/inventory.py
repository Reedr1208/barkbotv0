"""
BDW (Bideawee, New York NY) — Inventory Scraper

Bideawee's adoption page (https://www.bideawee.org/programs/adoption/) renders
its animal grid client-side from the Shelterluv v1 API:

    GET https://www.shelterluv.com/api/v1/animals?status_type=publishable
    X-Api-Key: <read-only key embedded in the site's public adopt.js>

We call the same endpoint (one request per run), keep only Type == "Dog"
(the feed also contains cats and other species), skip animals the site shows as
"I'm Adopted!" (attribute "Adopted for Gallery"), and full-replace this
shelter's active_dogs rows.

IDs: animal_id = "BDW-{Internal-ID}" (Shelterluv's stable internal animal ID,
also used in the site's profile URL /adopt-pet/{name-slug}/{Internal-ID}).

Locations: Bideawee has a Manhattan adoption center plus Long Island sites
(Westhampton, Wantagh) and foster homes. All dogs are listed under NYC; the
actual site is written into the bio by profiles.py.

No Playwright needed. Runs via APScheduler.
"""

import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests

from jobs.lib.db import get_supabase_client, now_iso, record_run_finish, record_run_start

SHELTER_ID = "BDW"
SHELTER_NAME = "Bideawee"
CITY = "NYC"
STATE = "NY"

LISTING_URL = "https://www.bideawee.org/programs/adoption/"
PROFILE_URL_TEMPLATE = "https://www.bideawee.org/adopt-pet/{slug}/{internal_id}"

SHELTERLUV_API = "https://www.shelterluv.com/api/v1/animals"
# Read-only "publishable animals" key that bideawee.org ships in its public
# adopt.js (every visitor's browser uses it). Override via env if it rotates.
SHELTERLUV_API_KEY = os.environ.get("BIDEAWEE_SHELTERLUV_API_KEY", "2a28d8ce-bc06-4573-bb6c-7c1828af54ee")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": LISTING_URL,
}

PAGE_SIZE = 100
MAX_PAGES = 20
# Bideawee typically lists ~20 dogs; fewer than this means something broke.
MIN_EXPECTED_DOGS = 3

ADOPTED_ATTRIBUTE = "Adopted for Gallery"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Shelterluv API helpers (shared with profiles.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _api_headers() -> Dict[str, str]:
    return {**HEADERS, "X-Api-Key": SHELTERLUV_API_KEY}


def fetch_publishable_animals(session: Optional[requests.Session] = None) -> List[Dict[str, Any]]:
    """All publishable animals (every species) from Shelterluv, following pagination."""
    sender = session or requests
    animals: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(MAX_PAGES):
        resp = sender.get(
            SHELTERLUV_API,
            params={"status_type": "publishable", "offset": offset, "limit": PAGE_SIZE},
            headers=_api_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", 1):
            raise RuntimeError(f"Shelterluv API returned success=0: {str(data)[:200]}")
        batch = data.get("animals") or []
        animals.extend(batch)
        if not data.get("has_more") or not batch:
            break
        offset += len(batch)
        time.sleep(1)
    return animals


def fetch_animal(internal_id: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """One animal by Shelterluv Internal-ID. Raises requests.HTTPError on 4xx/5xx."""
    sender = session or requests
    resp = sender.get(f"{SHELTERLUV_API}/{internal_id}", headers=_api_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def attribute_names(animal: Dict[str, Any], published_only: bool = False) -> List[str]:
    names = []
    for attr in animal.get("Attributes") or []:
        if published_only and str(attr.get("Publish", "")).lower() != "yes":
            continue
        name = (attr.get("AttributeName") or "").strip()
        if name:
            names.append(name)
    return names


def is_listable_dog(animal: Dict[str, Any]) -> bool:
    """Dogs only (no cats / rabbits / etc.), excluding ones the site shows as adopted."""
    if (animal.get("Type") or "").strip().lower() != "dog":
        return False
    return ADOPTED_ATTRIBUTE not in attribute_names(animal)


def clean_name(raw: str) -> str:
    """'Maddie (FKA Madison)' → 'Maddie'; trims stray whitespace."""
    name = re.sub(r"\s*\((?:fka|aka|formerly)\b[^)]*\)", "", raw or "", flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


def format_age(months: Any) -> str:
    """Shelterluv Age is in months → '10 years 8 months' / '7 months'."""
    try:
        m = int(months)
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    years, rem = divmod(m, 12)
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if rem:
        parts.append(f"{rem} month{'s' if rem != 1 else ''}")
    return " ".join(parts)


def format_weight(pounds: Any) -> str:
    try:
        value = float(pounds)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return f"{value:g} lbs"


def profile_url(animal: Dict[str, Any]) -> str:
    """Same URL the site's adopt.js links to (name lower-cased, whitespace → '-')."""
    slug = re.sub(r"\s+", "-", (animal.get("Name") or "").lower())
    return PROFILE_URL_TEMPLATE.format(slug=slug, internal_id=animal["Internal-ID"])


def animal_id_for(animal: Dict[str, Any]) -> str:
    return f"{SHELTER_ID}-{animal['Internal-ID']}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Inventory job
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_rows(animals: List[Dict[str, Any]], scraped_at: str) -> List[Dict[str, Any]]:
    rows, seen = [], set()
    for a in animals:
        if not is_listable_dog(a) or not a.get("Internal-ID"):
            continue
        aid = animal_id_for(a)
        if aid in seen:
            continue
        seen.add(aid)
        sex = (a.get("Sex") or "").strip()
        rows.append({
            "animal_id": aid,
            "name": clean_name(a.get("Name") or ""),
            "gender": sex if sex in ("Male", "Female") else None,
            "age": format_age(a.get("Age")),
            "weight": format_weight(a.get("CurrentWeightPounds")),
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": profile_url(a),
            "scraped_at": scraped_at,
            "shelter_id": SHELTER_ID,
        })
    return rows


def scrape_inventory() -> List[Dict[str, Any]]:
    """Fetch Bideawee's publishable animals, keep dogs, full-replace active_dogs."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_bdw_inventory")
    logging.info("Starting BDW inventory scrape...")

    try:
        animals = fetch_publishable_animals()
        rows = build_rows(animals, now_iso())
        logging.info(f"Fetched {len(animals)} publishable animals → {len(rows)} dogs")

        if len(rows) < MIN_EXPECTED_DOGS:
            # API change / key rotated / outage — keep the previous inventory
            # rather than wiping it (and cascading deletes of favorites/chats).
            raise RuntimeError(
                f"Parsed {len(rows)} dogs for {SHELTER_ID} from {len(animals)} Shelterluv animals "
                f"— API or key may have changed"
            )

        logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
        client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()
        logging.info(f"Inserting {len(rows)} dogs into active_dogs...")
        for i in range(0, len(rows), 100):
            client.table("active_dogs").insert(rows[i:i + 100]).execute()

        record_run_finish(client, run_id, "success", notes=json.dumps({"scraped_count": len(rows)}))
        logging.info("Done.")
        return rows

    except Exception as exc:
        logging.error(f"Inventory scrape failed: {exc}")
        record_run_finish(client, run_id, "error", notes=str(exc))
        raise


if __name__ == "__main__":
    scrape_inventory()
