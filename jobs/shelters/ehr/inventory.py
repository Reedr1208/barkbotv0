"""
EHR (Eleventh Hour Rescue) — Inventory Scraper

Scrapes adoptable dog listings from ehrdogs.org, which now uses the
Buzz Rescues WordPress theme. All dogs are rendered on a single page
at /dogs/ as server-rendered HTML cards.

Filters out catch-all tiles (generic application entries) whose names
start with '*' (e.g. "**A Puppy under 7 months", "*A dog 7+ months").

No Playwright needed — pure HTTP. Runs via APScheduler.
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

LISTING_URL = "https://ehrdogs.org/dogs/"
DETAIL_BASE = "https://ehrdogs.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def normalize_gender(raw: str) -> Optional[str]:
    """Normalize gender string."""
    if not raw:
        return None
    lower = raw.lower()
    if "female" in lower:
        return "Female"
    if "male" in lower:
        return "Male"
    return None


def extract_age(meta_div) -> str:
    """Extract age text from the Bzl-dog-meta div."""
    if not meta_div:
        return ""
    for div in meta_div.find_all("div", class_="col-12"):
        icon = div.find("i", class_=lambda c: c and "icon-cake" in c)
        if icon:
            text = div.get_text(strip=True)
            # Remove the icon's own text contribution (empty), just get the text
            return text
    return ""


def extract_breed(meta_div) -> str:
    """Extract breed text from the Bzl-dog-meta div."""
    if not meta_div:
        return ""
    for div in meta_div.find_all("div", class_="col-12"):
        icon = div.find("i", class_=lambda c: c and "icon-dog-face" in c)
        if icon:
            return div.get_text(strip=True)
    return ""


def extract_gender_from_meta(meta_div) -> Optional[str]:
    """Extract gender from the Bzl-dog-meta div."""
    if not meta_div:
        return None
    for div in meta_div.find_all("div", class_="col-12"):
        icon = div.find("i", class_=lambda c: c and ("icon-male-sign" in c or "icon-female-sign" in c))
        if icon:
            icon_class = " ".join(icon.get("class", []))
            if "icon-female-sign" in icon_class:
                text = div.get_text(strip=True)
                return "Female" if text else "Female"
            if "icon-male-sign" in icon_class:
                text = div.get_text(strip=True)
                return "Male" if text else "Male"
    return None


def generate_animal_id(profile_url: str, name: str) -> str:
    """Generate a stable animal_id from the profile URL slug.

    The Buzz Rescues theme uses WordPress slugs like /dog/alvin-dixon/.
    We use the slug as the unique identifier, prefixed with EHR-.
    """
    # Extract slug from URL like https://ehrdogs.org/dog/alvin-dixon/
    match = re.search(r"/dog/([^/]+)/?$", profile_url)
    if match:
        slug = match.group(1)
        return f"EHR-{slug}"
    # Fallback: generate from name
    if name:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return f"EHR-{slug}"
    return ""


def parse_listing_page(html_content: str) -> List[Dict]:
    """Parse dog cards from the /dogs/ page.

    Each dog is a <div class="Bzl-dog-post"> with structured data attributes
    and nested HTML containing name, breed, gender, age, and profile URL.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find all dog post cards
    cards = soup.find_all("div", class_="Bzl-dog-post")

    rows = []
    for card in cards:
        # Get name from data attribute or heading link
        data_name = card.get("data-name", "").strip()

        # Skip catch-all tiles (generic application entries starting with *)
        if data_name.startswith("*"):
            continue

        # Get the heading link for name and profile URL
        heading_div = card.find("div", class_="Bzl-dog-heading")
        if not heading_div:
            continue

        heading_link = heading_div.find("a")
        if not heading_link:
            continue

        name = heading_link.get("title", "") or heading_link.get_text(strip=True)
        profile_url = heading_link.get("href", "")

        # Make sure profile URL is absolute
        if profile_url and not profile_url.startswith("http"):
            profile_url = DETAIL_BASE + profile_url

        # Skip entries without a name
        if not name:
            continue

        # Generate animal ID from the profile URL slug
        animal_id = generate_animal_id(profile_url, name)
        if not animal_id:
            continue

        # Extract gender — prefer data attribute, fall back to meta icons
        data_gender = card.get("data-gender", "").strip()
        meta_div = card.find("div", class_="Bzl-dog-meta")

        gender = normalize_gender(data_gender)
        if not gender:
            gender = extract_gender_from_meta(meta_div)

        # Extract age from meta
        age = extract_age(meta_div)

        rows.append({
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "age": age,
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
        logging.info(f"Fetching {LISTING_URL}...")

        resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        all_rows = parse_listing_page(resp.text)

        # Deduplicate by animal_id
        seen_ids = set()
        unique_rows = []
        for row in all_rows:
            if row["animal_id"] not in seen_ids:
                seen_ids.add(row["animal_id"])
                row["scraped_at"] = now_iso()
                unique_rows.append(row)

        logging.info(f"Total unique dogs: {len(unique_rows)}")

        if unique_rows:
            logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
            client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()

            logging.info(f"Inserting {len(unique_rows)} dogs into active_dogs...")
            for chunk_start in range(0, len(unique_rows), 100):
                chunk = unique_rows[chunk_start:chunk_start + 100]
                client.table("active_dogs").insert(chunk).execute()
            logging.info("Insert complete.")

        notes = {"scraped_count": len(unique_rows)}
        record_run_finish(client, run_id, "success", notes=json.dumps(notes))
        logging.info("Done.")

    except Exception as exc:
        logging.error(f"Inventory scrape failed: {exc}")
        record_run_finish(client, run_id, "error", notes=str(exc))
        raise


if __name__ == "__main__":
    scrape_inventory()
