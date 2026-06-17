"""
RDR (Rocket Dog Rescue) — Profile Scraper

Fetches individual dog profile pages from Shelterluv embeds and extracts
structured fields + bio text.

Each Shelterluv profile page contains a `:animal` attribute with a JSON blob
containing all structured data including:
- name, sex, breed, secondary_breed, weight, weight_units
- birthday, age_group
- primary_color, secondary_color
- kennel_description (the bio/narrative text)
- photos dict
- public_url

No Playwright needed — the JSON is embedded in the initial HTML response.
Runs via Vercel crons.
"""

import html
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "RDR"
SHELTER_NAME = "Rocket Dog Rescue"
CITY = "San Francisco"
STATE = "CA"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_animal_json(page_html: str) -> Optional[Dict]:
    """Extract the embedded :animal JSON from a Shelterluv profile page."""
    # The JSON is HTML-entity-encoded in a :animal="..." attribute
    match = re.search(r':animal="({.*?})"', page_html)
    if not match:
        return None

    raw = match.group(1)
    decoded = html.unescape(raw)
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return None


def _extract_cover_photo(animal_data: Dict) -> Optional[str]:
    """Get the cover photo URL from the photos dict or list."""
    photos = animal_data.get("photos", {})
    if not photos:
        return None

    # Normalize: photos can be a dict or a list depending on the animal
    photo_items = []
    if isinstance(photos, dict):
        photo_items = list(photos.values())
    elif isinstance(photos, list):
        photo_items = photos

    # Try to find isCover first
    for photo in photo_items:
        if isinstance(photo, dict) and photo.get("isCover"):
            return photo.get("url")

    # Fallback to the first photo
    for photo in photo_items:
        if isinstance(photo, dict) and photo.get("url"):
            return photo["url"]

    return None


def _age_from_birthday(birthday_ts: str) -> str:
    """Calculate human-readable age from unix timestamp birthday."""
    try:
        born = datetime.fromtimestamp(int(birthday_ts), tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - born
        years = delta.days // 365
        months = (delta.days % 365) // 30
        if years > 0:
            return f"{years} year{'s' if years != 1 else ''}" + (f" {months} month{'s' if months != 1 else ''}" if months else "")
        return f"{months} month{'s' if months != 1 else ''}"
    except (ValueError, TypeError, OSError):
        return ""


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single Shelterluv dog profile page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    animal_data = _extract_animal_json(resp.text)

    if not animal_data:
        # Fallback: try og:description at minimum
        soup = BeautifulSoup(resp.text, "html.parser")
        og_desc = soup.find("meta", property="og:description")
        bio = og_desc["content"] if og_desc and og_desc.get("content") else ""
        og_img = soup.find("meta", property="og:image")
        image_url = og_img["content"] if og_img and og_img.get("content") else None
        
        return {
            "shelter_profile_url": url,
            "animal_id": target["animal_id"],
            "shelter_name": SHELTER_NAME,
            "name": target.get("name", ""),
            "gender": target.get("gender", ""),
            "age": target.get("age", ""),
            "weight": "",
            "more_info": "",
            "bio": bio,
            "shelter_image_url": image_url,
            "image_file": None,
            "image_public_url": None,
            "city": CITY,
            "state": STATE,
            "shelter_id": SHELTER_ID,
        }

    # Extract structured fields
    name = animal_data.get("name", target.get("name", "")).strip()
    gender = animal_data.get("sex", "").strip()
    breed = animal_data.get("breed", "").strip()
    secondary_breed = animal_data.get("secondary_breed", "").strip()
    
    # Weight
    weight_val = animal_data.get("weight")
    weight_units = animal_data.get("weight_units", "lbs")
    weight = f"{weight_val} {weight_units}" if weight_val else animal_data.get("weight_group", "")
    
    # Age
    age = ""
    birthday = animal_data.get("birthday")
    if birthday:
        age = _age_from_birthday(birthday)
    if not age:
        age_group = animal_data.get("age_group")
        if age_group and isinstance(age_group, dict):
            age = age_group.get("name_with_duration") or age_group.get("name") or ""
    
    # Colors
    primary_color = animal_data.get("primary_color", "")
    secondary_color = animal_data.get("secondary_color", "")
    
    # Build bio
    bio_parts = []
    if breed:
        full_breed = breed
        if secondary_breed:
            full_breed += f" / {secondary_breed}"
        bio_parts.append(f"Breed: {full_breed}")
    if gender:
        bio_parts.append(f"Gender: {gender}")
    if age:
        bio_parts.append(f"Age: {age}")
    if weight:
        bio_parts.append(f"Weight: {weight}")
    if primary_color:
        color = primary_color
        if secondary_color:
            color += f" / {secondary_color}"
        bio_parts.append(f"Color: {color}")
    
    # Narrative bio from kennel_description
    narrative = (animal_data.get("kennel_description") or "").strip()
    if narrative:
        # Clean HTML tags from narrative
        narrative = re.sub(r'<[^>]+>', ' ', narrative)
        narrative = re.sub(r'\s+', ' ', narrative).strip()
        bio_parts.append("")
        bio_parts.append(narrative)
    
    bio = "\n".join(bio_parts)
    
    image_url = _extract_cover_photo(animal_data)
    
    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name,
        "gender": gender or target.get("gender", ""),
        "age": age or target.get("age", ""),
        "weight": weight,
        "more_info": "",
        "bio": bio,
        "shelter_image_url": image_url,
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    return run_profiles_scrape(
        shelter_id=SHELTER_ID,
        fetch_record_fn=fetch_record,
        headers=HEADERS,
        extra_fields=["age"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
