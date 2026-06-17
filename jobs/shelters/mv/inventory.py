"""
MV (Muttville Senior Dog Rescue) — Inventory Scraper

Scrapes adoptable dog listings from muttville.org/available_mutts.
All dogs are listed on a single page as links to /mutt/{slug} detail pages.
The slug format is {name}-{id} where id is a numeric Muttville ID.

No Playwright needed — pure HTTP. Runs via Vercel crons.
"""

import json
import logging
import re
import sys
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "MV"
SHELTER_NAME = "Muttville Senior Dog Rescue"
CITY = "San Francisco"
STATE = "CA"

LISTING_URL = "https://muttville.org/available_mutts"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def parse_listing_page(html_content: str, scraped_at: str) -> List[Dict]:
    """Parse dog links from the listing page."""
    soup = BeautifulSoup(html_content, "html.parser")

    links = soup.find_all("a", href=re.compile(r"/mutt/"))
    logging.info(f"Found {len(links)} /mutt/ links")

    rows = []
    seen_ids = set()

    for link in links:
        href = link.get("href", "")
        slug = href.split("/mutt/")[-1] if "/mutt/" in href else ""
        if not slug:
            continue

        # Extract numeric ID from slug (e.g. "bravo-14147" -> "14147")
        id_match = re.search(r"-(\d+)$", slug)
        if not id_match:
            continue

        mutt_id = id_match.group(1)
        if mutt_id in seen_ids:
            continue
        seen_ids.add(mutt_id)

        name = link.get_text(strip=True)
        # Clean name — some have "Hospice" appended
        name = re.sub(r"\s*Hospice\s*$", "", name).strip()

        if not name:
            continue

        animal_id = f"MV-{mutt_id}"
        profile_url = f"https://muttville.org/mutt/{slug}"

        rows.append({
            "animal_id": animal_id,
            "name": name,
            "gender": None,
            "age": "",
            "weight": "",
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": profile_url,
            "scraped_at": scraped_at,
            "shelter_id": SHELTER_ID,
        })

    return rows


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_mv_inventory")

    logging.info("Starting MV inventory scrape...")

    try:
        resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        scraped_at = now_iso()
        all_rows = parse_listing_page(resp.text, scraped_at)

        logging.info(f"Parsed {len(all_rows)} dogs")

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
