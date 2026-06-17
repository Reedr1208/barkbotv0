"""
NHS (Nassau Humane Society) — Inventory Scraper

Uses the PetPoint/Petango web services API to fetch adoptable dog listings.
The shelter embeds a Petango iframe on their site; we hit the same endpoint
directly. Already filtered to species=Dog.

No Playwright needed — pure HTTP requests. Runs via Vercel crons.
"""

import json
import logging
import re
import sys
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "NHS"
SHELTER_NAME = "Nassau Humane Society"
CITY = "Jacksonville"
STATE = "FL"

# Petango listing endpoint — already filtered to Dogs
PETANGO_LISTING_URL = (
    "https://ws.petango.com/webservices/adoptablesearch/wsAdoptableAnimals2.aspx"
    "?species=Dog&sex=A&agegroup=All&onhold=A&orderby=Name&colnum=4"
    "&AuthKey=77d41vfvhgl433bdyw5n47nihc200605mbjakwq1q2rapyf2mg"
)

PETANGO_DETAIL_BASE = (
    "https://ws.petango.com/webservices/adoptablesearch/"
    "wsAdoptableAnimalDetails2.aspx"
    "?id={pet_id}&css=&authkey=77d41vfvhgl433bdyw5n47nihc200605mbjakwq1q2rapyf2mg"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def normalize_gender(raw: str) -> Optional[str]:
    """Normalize gender from Petango format like 'Male/Neutered'."""
    if not raw:
        return None
    lower = raw.lower()
    if "female" in lower:
        return "Female"
    if "male" in lower:
        return "Male"
    return None


def parse_listing_page(html_content: str, scraped_at: str) -> List[Dict]:
    """Parse dog cards from the Petango listing HTML."""
    soup = BeautifulSoup(html_content, "html.parser")

    cards = soup.find_all("div", class_="list-animal-info-block")
    logging.info(f"Found {len(cards)} cards in listing page")

    rows = []
    seen_ids = set()

    # Also extract detail page links for the pet IDs
    links = soup.find_all("a", href=True)

    # Build a map of pet IDs to their detail URLs
    # Cards and links appear in alternating order — link first (image), then link (name)
    pet_ids_in_order = []
    for link in links:
        href = link.get("href", "")
        if "wsAdoptableAnimalDetails" in href:
            match = re.search(r"id=(\d+)", href)
            if match:
                pid = match.group(1)
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    pet_ids_in_order.append(pid)

    # Reset for card processing
    seen_ids = set()

    for i, card in enumerate(cards):
        # Extract text lines from the card
        text_parts = [t.strip() for t in card.get_text(separator="|", strip=True).split("|") if t.strip()]

        if len(text_parts) < 3:
            continue

        name = text_parts[0]
        # text_parts[1] is "Dog" (species)
        gender_raw = text_parts[2] if len(text_parts) > 2 else ""
        breed = text_parts[3] if len(text_parts) > 3 else ""
        age = text_parts[4] if len(text_parts) > 4 else ""

        # Get pet ID from the ordered list
        pet_id = pet_ids_in_order[i] if i < len(pet_ids_in_order) else None
        if not pet_id or pet_id in seen_ids:
            continue
        seen_ids.add(pet_id)

        animal_id = f"NHS-{pet_id}"
        profile_url = PETANGO_DETAIL_BASE.format(pet_id=pet_id)

        rows.append({
            "animal_id": animal_id,
            "name": name,
            "gender": normalize_gender(gender_raw),
            "age": age,
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
    run_id = record_run_start(client, "cron_nhs_inventory")

    logging.info("Starting NHS inventory scrape...")

    try:
        resp = requests.get(PETANGO_LISTING_URL, headers=HEADERS, timeout=30)
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
