"""
RDR (Rocket Dog Rescue) — Inventory Scraper

Scrapes adoptable dog listings via the public Shelterluv V3 API.
The API endpoint provides a full list of available dogs in JSON format.
We extract basic metadata, avoiding the need for Playwright or pagination logic.

No Playwright needed — pure HTTP. Runs via Vercel crons.
"""

import json
import logging
import sys
from typing import Dict, List

import requests

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "RDR"
SHELTER_NAME = "Rocket Dog Rescue"
CITY = "San Francisco"
STATE = "CA"

# GID 184 is Rocket Dog Rescue's Shelterluv ID
API_URL = "https://new.shelterluv.com/api/v3/available-animals/184?species=Dog"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json"
}


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_rdr_inventory")
    
    logging.info("Starting RDR inventory scrape...")
    
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        animals = data.get("animals", [])
        logging.info(f"Fetched {len(animals)} dogs from Shelterluv API")
        
        all_rows: List[Dict] = []
        scraped_at = now_iso()
        
        for animal in animals:
            nid = animal.get("nid")
            name = animal.get("name", "").strip()
            
            if not nid or not name:
                continue
            
            animal_id = f"{SHELTER_ID}-{nid}"
            profile_url = animal.get("public_url") or f"https://new.shelterluv.com/embed/animal/{nid}"
            
            # Extract gender
            gender = animal.get("sex", "")
            
            # Extract age
            age = ""
            age_group = animal.get("age_group")
            if age_group and isinstance(age_group, dict):
                age = age_group.get("name_with_duration") or age_group.get("name") or ""
            
            # Extract weight
            weight = animal.get("weight_group", "")
            
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
