"""
PACC (Pima Animal Care Center) — Inventory Scraper

Scrapes adoptable dog listings from 24petconnect.com/PimaAdoptablePets
and replaces the active_dogs table entries for PACC.
"""

import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client

GET_ALL_PAGES = True

BASE_URL = "https://24petconnect.com/PimaAdoptablePets"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def build_url(index: int) -> str:
    params = {
        "at": "DOG",
        "sb": "id_asc",
    }
    if index > 0:
        params["index"] = index
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_page(index: int, retries: int = 3) -> str:
    url = build_url(index)

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            if attempt == retries:
                raise
            print(f"Retrying index={index} after error: {e}")
            time.sleep(2 * attempt)


def get_total_count(page_text: str) -> int | None:
    match = re.search(r"Animals:\s+\d+\s+-\s+\d+\s+of\s+(\d+)", page_text)
    return int(match.group(1)) if match else None


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_dogs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    dogs = []

    for card in soup.select("div.gridResult"):
        def field(name: str) -> str:
            el = card.select_one(f".text_{name}")
            return clean(el.get_text(" ", strip=True)) if el else ""

        onclick = card.get("onclick", "")
        match = re.search(r"Details\('([^']*)',\s*'([^']*)',\s*'([^']*)'\)", onclick)
        if match:
            shelter_profile_url = f"https://24petconnect.com/{match.group(1)}/Details/{match.group(2)}/{match.group(3)}"
        else:
            shelter_profile_url = f"https://24petconnect.com/PimaAdoptablePets/Details/PIMA/{field('AnimalID')}"

        dogs.append({
            "animal_id": f"PACC-{field('AnimalID')}",
            "name": field("Name").replace("*", "").strip().title(),
            "gender": field("Gender"),
            "age": field("Age"),
            "weight": field("Weight"),
            "city": "Tucson",
            "state": "AZ",
            "shelter_name": "Pima Animal Care Center",
            "shelter_profile_url": shelter_profile_url,
            "scraped_at": now_iso()
        })

    return dogs


def scrape_all_dogs() -> list[dict]:
    all_dogs = []
    seen_ids = set()
    index = 0
    total_count = None

    while True:
        if (not GET_ALL_PAGES) and index > 0:
            break
        print(f"Fetching dogs starting at index {index}...")
        html = fetch_page(index)

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text("\n", strip=True)

        if total_count is None:
            total_count = get_total_count(page_text)
            if total_count:
                print(f"Reported total dogs: {total_count}")

        dogs = parse_dogs(html)

        if not dogs:
            print("No dogs found on this page. Stopping.")
            break

        new_count = 0
        for dog in dogs:
            if dog["animal_id"] not in seen_ids:
                all_dogs.append(dog)
                seen_ids.add(dog["animal_id"])
                new_count += 1

        print(f"Parsed {len(dogs)} dogs; {new_count} new.")

        index += 30

        if total_count is not None and len(all_dogs) >= total_count:
            break

        # Safety stop in case the site gives repeated pages forever.
        if new_count == 0:
            print("No new animal IDs found. Stopping.")
            break

        time.sleep(2)

    return all_dogs


def save_to_supabase(dogs: list[dict]):
    if not dogs:
        print("No dogs to save.")
        return

    # Safety check: ensure we have a meaningful amount of data before wiping the table
    if len(dogs) < 30:
        raise RuntimeError(f"Safety check failed: Only {len(dogs)} dogs scraped. Aborting to prevent accidental data loss.")

    client = get_supabase_client()

    print("Clearing existing active_dogs table data for PACC...")
    # Delete all rows for PACC.
    client.table("active_dogs").delete().eq("shelter_id", "PACC").execute()

    print(f"Inserting {len(dogs)} dogs into active_dogs...")

    # Ensure shelter_id is set
    for dog in dogs:
        dog["shelter_id"] = "PACC"

    # We may need to chunk inserts if there are too many, but Supabase can handle a few hundred fine.
    client.table("active_dogs").insert(dogs).execute()


if __name__ == "__main__":
    dogs = scrape_all_dogs()
    save_to_supabase(dogs)
    print(f"Done. Wrote {len(dogs)} dogs to active_dogs table in Supabase.")
