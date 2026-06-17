"""
EHR (Eleventh Hour Rescue) — Inventory Scraper

Scrapes adoptable dog listings from ehrdogs.org, which uses RescueGroups.
The listing is paginated (~21 dogs per page) and pages loop after all
dogs are shown. We stop when we see repeated IDs.

Filters out two catch-all tiles (generic application entries):
  - "**A Puppy 6 Months and Under"  (AnimalID 22543099)
  - "*A Dog 7 Months and Older"     (AnimalID 22543103)

No Playwright needed — pure HTTP. Runs via Vercel crons.
"""

import json
import logging
import re
import sys
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "EHR"
SHELTER_NAME = "Eleventh Hour Rescue"
CITY = "Dover"
STATE = "NJ"

LISTING_URL = "https://www.ehrdogs.org/animals/browse"
DETAIL_BASE = "https://www.ehrdogs.org/animals/detail?AnimalID={animal_id}"

# Catch-all tile IDs to exclude (generic application entries, not real dogs)
EXCLUDED_IDS = {"22543099", "22543103"}

MAX_PAGES = 60  # Safety limit — should only need ~20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def normalize_gender(raw: str) -> Optional[str]:
    """Normalize gender from RescueGroups format."""
    if not raw:
        return None
    lower = raw.lower()
    if "female" in lower:
        return "Female"
    if "male" in lower:
        return "Male"
    return None


def parse_listing_page(html_content: str) -> List[Dict]:
    """Parse dog cards from a single listing page. Returns list of {animal_id, name, breed, gender, age}."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Find all detail links
    links = soup.find_all("a", href=True)
    
    # Build ordered list of unique animal IDs on this page
    seen = set()
    ids_on_page = []
    for link in links:
        href = link.get("href", "")
        match = re.search(r"AnimalID=(\d+)", href)
        if match:
            aid = match.group(1)
            if aid not in seen:
                seen.add(aid)
                ids_on_page.append(aid)
    
    # Parse the text structure — animals appear as blocks in the page text
    body_text = soup.get_text(separator="\n", strip=True)
    lines = body_text.split("\n")
    
    rows = []
    for raw_id in ids_on_page:
        if raw_id in EXCLUDED_IDS:
            continue
        
        animal_id = f"EHR-{raw_id}"
        profile_url = DETAIL_BASE.format(animal_id=raw_id)
        
        # Find the name and breed from links near this ID
        name = ""
        breed = ""
        gender = None
        
        for link in links:
            href = link.get("href", "")
            if f"AnimalID={raw_id}" in href:
                text = link.get_text(strip=True)
                if text and "Click for more" not in text and not text.startswith("*"):
                    name = text
                    break
        
        # Find breed/gender near this name in the page text
        for i, line in enumerate(lines):
            if line.strip() == name and i + 4 < len(lines):
                # Next lines after name: Breed:, breed_value, Species/Sex:, sex_value
                for j in range(i + 1, min(i + 8, len(lines))):
                    if lines[j].strip() == "Breed:":
                        if j + 1 < len(lines):
                            breed = lines[j + 1].strip()
                    if "Species/Sex:" in lines[j] or "Species:" in lines[j]:
                        val = lines[j].replace("Species/Sex:", "").replace("Species:", "").strip()
                        if not val and j + 1 < len(lines):
                            val = lines[j + 1].strip()
                        gender = normalize_gender(val)
                break
        
        # Filter out cats
        if "kitten" in name.lower():
            continue
        breed_lower = breed.lower()
        if "cat" in breed_lower or "feline" in breed_lower or "domestic" in breed_lower:
            continue
        
        rows.append({
            "raw_id": raw_id,
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "age": "",
            "weight": "",
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": profile_url,
            "shelter_id": SHELTER_ID,
        })
    
    return rows


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_ehr_inventory")
    
    logging.info("Starting EHR inventory scrape...")
    
    try:
        all_rows: List[Dict] = []
        seen_ids = set()
        
        for page_num in range(1, MAX_PAGES + 1):
            url = f"{LISTING_URL}?Species=Dog&page={page_num}"
            logging.info(f"Fetching page {page_num}...")
            
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            
            page_rows = parse_listing_page(resp.text)
            
            if not page_rows:
                logging.info(f"No dogs on page {page_num}, stopping.")
                break
            
            # Check for loops — if all IDs already seen, we've wrapped around
            new_ids = [r["raw_id"] for r in page_rows if r["raw_id"] not in seen_ids]
            if not new_ids:
                logging.info(f"Page {page_num}: all IDs already seen, stopping (pagination looped).")
                break
            
            for row in page_rows:
                if row["raw_id"] not in seen_ids:
                    seen_ids.add(row["raw_id"])
                    # Remove raw_id before DB insert
                    db_row = dict(row)
                    db_row.pop("raw_id", None)
                    db_row["scraped_at"] = now_iso()
                    all_rows.append(db_row)
            
            logging.info(f"Page {page_num}: {len(new_ids)} new dogs (total: {len(all_rows)})")
        
        logging.info(f"Total unique dogs: {len(all_rows)}")
        
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
