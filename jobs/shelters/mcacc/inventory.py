"""
MCACC (Maricopa County Animal Care and Control) — Inventory Scraper

Scrapes adoptable dogs from the Maricopa County shelter website.
The site uses an ASP.NET MVC backend that returns server-rendered HTML partials,
so no Playwright is needed — plain HTTP GET requests with BeautifulSoup suffice.

Inventory endpoint:
  GET https://apps.pets.maricopa.gov/adoptPets/Home/AnimalGrid
  Params: animalTypeFilter=Dog, pageNumber=N, etc.
  Returns: HTML partial with .dogCard divs containing onclick handlers
           like ShowDetailsForAnimal('A5164514')

Animal ID pattern: A5164514 → MCACC-5164514 (strip leading "A")
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client

# ── Config ────────────────────────────────────────────────────────────────
SHELTER_ID = "MCACC"
SHELTER_NAME = "Maricopa County Animal Care and Control"
CITY = "Phoenix"
STATE = "AZ"

GRID_URL = "https://apps.pets.maricopa.gov/adoptPets/Home/AnimalGrid"
DETAIL_URL_TEMPLATE = "https://apps.pets.maricopa.gov/adoptPets/Home/Details/{animal_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

# Safety: don't replace the DB if we scraped fewer than this many dogs
MIN_DOG_THRESHOLD = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _extract_animal_id(onclick: str) -> Optional[str]:
    """Extract animal ID from onclick='ShowDetailsForAnimal('A5164514')'."""
    m = re.search(r"ShowDetailsForAnimal\('(A\d+)'\)", onclick)
    return m.group(1) if m else None


def _format_animal_id(raw_id: str) -> str:
    """Convert raw ID like 'A5164514' to our format 'MCACC-5164514'."""
    numeric = raw_id.lstrip("A")
    return f"{SHELTER_ID}-{numeric}"


def _scrape_page(session: requests.Session, page_number: int) -> List[dict]:
    """Scrape a single page of the animal grid, filtering for dogs only."""
    params = {
        "animalTypeFilter": "Dog",
        "pageNumber": page_number,
        "sizeFilter": 1,
        "ageFilter": 1,
        "genderFilter": 1,
        "breedFilter": "Any Breed",
        "shelterFilter": "All",
    }

    resp = session.get(GRID_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    dogs = []
    # Find all elements with ShowDetailsForAnimal onclick
    for el in soup.find_all(attrs={"onclick": True}):
        raw_id = _extract_animal_id(el["onclick"])
        if not raw_id:
            continue

        animal_id = _format_animal_id(raw_id)

        # Navigate up to the card container to extract more info
        card = el.find_parent("div", class_=True)

        # Extract name
        name = ""
        name_span = None
        if card:
            name_span = card.find("span", class_="searchPetTitleSpan")
        if not name_span:
            # Search wider
            name_span = soup.find("span", class_="searchPetTitleSpan")
        # Try extracting from the card's parent structure
        parent = el
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            ns = parent.find("span", class_="searchPetTitleSpan")
            if ns:
                name = ns.text.strip()
                break

        # Extract age and sex from searchPetInfoAgeSex div
        age = ""
        gender = ""
        info_parent = el
        for _ in range(5):
            info_parent = info_parent.parent
            if info_parent is None:
                break
            info_div = info_parent.find("div", class_="searchPetInfoAgeSex")
            if info_div:
                spans = info_div.find_all("span")
                texts = [s.text.strip() for s in spans if s.text.strip()]
                if len(texts) >= 1:
                    age = texts[0]
                if len(texts) >= 2:
                    gender = texts[1]
                break

        profile_url = DETAIL_URL_TEMPLATE.format(animal_id=raw_id)

        dogs.append({
            "animal_id": animal_id,
            "name": name.title() if name else "",
            "gender": gender,
            "age": age,
            "weight": "",
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": profile_url,
            "scraped_at": now_iso(),
            "shelter_id": SHELTER_ID,
        })

    return dogs


def _scrape_all_pages(session: requests.Session) -> List[dict]:
    """Paginate through all pages and collect all dogs."""
    all_dogs = []
    seen_ids = set()
    page = 0
    max_pages = 50  # Safety limit (~21 dogs/page * 50 = ~1050 max)

    while page < max_pages:
        page_dogs = _scrape_page(session, page)

        if not page_dogs:
            logging.info(f"Page {page}: no dogs found, stopping pagination.")
            break

        # Deduplicate (each card appears once with onclick, but cards also
        # have favorite buttons with updateCookie/removeDogFromCookie)
        new_dogs = []
        for d in page_dogs:
            if d["animal_id"] not in seen_ids:
                seen_ids.add(d["animal_id"])
                new_dogs.append(d)

        if not new_dogs:
            logging.info(f"Page {page}: all dogs already seen, stopping.")
            break

        all_dogs.extend(new_dogs)
        logging.info(f"Page {page}: scraped {len(new_dogs)} new dogs (total: {len(all_dogs)})")
        page += 1

    return all_dogs


def main() -> int:
    """Main entry point for the MCACC inventory scraper."""
    session = requests.Session()
    dogs = _scrape_all_pages(session)

    logging.info(f"Total dogs scraped: {len(dogs)}")

    if len(dogs) < MIN_DOG_THRESHOLD:
        logging.error(
            f"Only {len(dogs)} dogs scraped — below safety threshold of {MIN_DOG_THRESHOLD}. "
            f"Aborting DB write to prevent data loss."
        )
        return 1

    # Full-replace pattern: clear existing, then insert
    client = get_supabase_client()

    logging.info(f"Clearing existing active_dogs table data for {SHELTER_ID}...")
    client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()

    logging.info(f"Inserting {len(dogs)} dogs into active_dogs...")
    # Insert in batches of 50
    batch_size = 50
    for i in range(0, len(dogs), batch_size):
        batch = dogs[i:i + batch_size]
        client.table("active_dogs").insert(batch).execute()

    logging.info("Insert complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
