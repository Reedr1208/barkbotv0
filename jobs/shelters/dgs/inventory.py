"""
DGS (Dog Gone Seattle) — Inventory Scraper

Fetches adoptable dog listings via the RescueGroups.org public API (v5).
Dog Gone Seattle uses a RescueGroups toolkit on their website; the same
API key provides access to their animals in JSON format.

No Playwright needed — pure HTTP. Runs via scheduler.
"""

import json
import logging
import re
import sys
from typing import Dict, List

import requests

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "DGS"
SHELTER_NAME = "Dog Gone Seattle"
CITY = "Seattle"
STATE = "WA"

# RescueGroups v5 public API
API_BASE = "https://api.rescuegroups.org/v5/public/animals/search/available"
API_KEY = "xVFWqhU8"  # Dog Gone Seattle's RescueGroups toolkit key

HEADERS = {
    "Content-Type": "application/vnd.api+json",
    "Authorization": API_KEY,
}

# Dog Gone Seattle profile link pattern
# action_0=pet tells the RescueGroups toolkit to show the individual pet page
PROFILE_URL_TEMPLATE = "https://doggoneseattle.org/adoptable-dogs/#action_0=pet&animalID_0={rg_id}&petIndex_0=0"

# Maximum pages to paginate through (safety valve)
MAX_PAGES = 10


def _clean_html(html_str: str) -> str:
    """Strip HTML tags from a string."""
    if not html_str:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html_str)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_dgs_inventory")

    logging.info("Starting DGS inventory scrape via RescueGroups API...")

    try:
        all_rows: List[Dict] = []
        scraped_at = now_iso()
        page = 1

        while page <= MAX_PAGES:
            params = {
                "limit": 100,
                "page": page,
                "sort": "animals.name",
            }

            # POST with org name filter
            body = {
                "data": {
                    "filters": [
                        {
                            "fieldName": "orgs.name",
                            "operation": "contains",
                            "criteria": "Dog Gone",
                        }
                    ]
                }
            }

            resp = requests.post(API_BASE, headers=HEADERS, params=params, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            animals = data.get("data", [])
            meta = data.get("meta", {})
            total = meta.get("count", 0)

            logging.info(f"Page {page}: fetched {len(animals)} dogs (total: {total})")

            if not animals:
                break

            for animal in animals:
                rg_id = animal.get("id")
                attrs = animal.get("attributes", {})
                name = (attrs.get("name") or "").strip()

                if not rg_id or not name:
                    continue

                animal_id = f"{SHELTER_ID}-{rg_id}"
                profile_url = PROFILE_URL_TEMPLATE.format(rg_id=rg_id)

                # Extract gender
                gender = attrs.get("sex", "")

                # Extract age
                age = attrs.get("ageString", "")

                # Extract weight (RescueGroups doesn't always have precise weight)
                weight = attrs.get("sizeGroup", "")

                all_rows.append({
                    "animal_id": animal_id,
                    "name": name,
                    "gender": gender,
                    "age": age,
                    "weight": weight,
                    "city": CITY,
                    "state": STATE,
                    "shelter_name": SHELTER_NAME,
                    "shelter_profile_url": profile_url,
                    "scraped_at": scraped_at,
                    "shelter_id": SHELTER_ID,
                })

            # Check if there are more pages
            total_pages = meta.get("pages", 1)
            if page >= total_pages:
                break
            page += 1

        logging.info(f"Parsed {len(all_rows)} dogs total")

        if all_rows:
            logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
            client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()

            logging.info(f"Inserting {len(all_rows)} dogs into active_dogs...")
            for chunk_start in range(0, len(all_rows), 100):
                chunk = all_rows[chunk_start:chunk_start + 100]
                client.table("active_dogs").insert(chunk).execute()
            logging.info("Insert complete.")

        notes = {"scraped_count": len(all_rows)}
        record_run_finish(client, run_id, "success", notes=json.dumps(notes))
        logging.info("Done.")

    except Exception as exc:
        logging.error(f"Inventory scrape failed: {exc}")
        record_run_finish(client, run_id, "error", notes=str(exc))
        raise


if __name__ == "__main__":
    scrape_inventory()
