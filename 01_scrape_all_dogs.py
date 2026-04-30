import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from supabase import create_client

GET_ALL_PAGES = True

BASE_URL = "https://24petconnect.com/PimaAdoptablePets"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

DEBUG_HTML_DIR = Path("html_debug")
DEBUG_HTML_DIR.mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_supabase_client():
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


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

        img = card.select_one("img")

        dogs.append({
            "animal_id": field("AnimalID"),
            "name": field("Name"),
            "gender": field("Gender"),
            "age": field("Age"),
            "weight": field("Weight"),
            "location": field("Location"),
            "view_type": field("ViewType"),
            "image_url": img.get("src", "") if img else "",
            "scraped_at": now_iso()
        })

    return dogs


def scrape_all_dogs() -> list[dict]:
    all_dogs = []
    seen_ids = set()
    index = 0
    total_count = None

    while True:
        if (not GET_ALL_PAGES) and index>0:
            break
        print(f"Fetching dogs starting at index {index}...")
        html = fetch_page(index)
        filepath = DEBUG_HTML_DIR / f"index_{index}.html"
        filepath.write_text(html, encoding="utf-8")

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

    client = get_supabase_client()

    print("Clearing existing pima_all_dogs table data...")
    # Delete all rows. neq("animal_id", "dummy") matches all valid records.
    client.table("pima_all_dogs").delete().neq("animal_id", "dummy").execute()

    print(f"Inserting {len(dogs)} dogs into pima_all_dogs...")
    
    # We may need to chunk inserts if there are too many, but Supabase can handle a few hundred fine.
    client.table("pima_all_dogs").insert(dogs).execute()


if __name__ == "__main__":
    dogs = scrape_all_dogs()
    save_to_supabase(dogs)
    print(f"Done. Wrote {len(dogs)} dogs to pima_all_dogs table in Supabase.")
