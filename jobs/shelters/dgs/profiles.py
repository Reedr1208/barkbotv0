"""
DGS (Dog Gone Seattle) — Profile Scraper

Fetches individual dog profile data from the RescueGroups.org public API (v5).
Each call fetches the full animal record including description, breed, photos,
and other structured data.

No Playwright needed — pure HTTP. Runs via scheduler.
"""

import json
import logging
import re
import sys
from typing import Any, Dict, Optional

import requests

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "DGS"
SHELTER_NAME = "Dog Gone Seattle"
CITY = "Seattle"
STATE = "WA"

# RescueGroups v5 public API
API_BASE = "https://api.rescuegroups.org/v5/public/animals"
API_KEY = "xVFWqhU8"

HEADERS = {
    "Content-Type": "application/vnd.api+json",
    "Authorization": API_KEY,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _extract_rg_id(animal_id: str) -> str:
    """Extract RescueGroups numeric ID from our animal_id format (DGS-12345678)."""
    return animal_id.replace(f"{SHELTER_ID}-", "")


def _clean_html(html_str: str) -> str:
    """Strip HTML tags and entities from a string."""
    if not html_str:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html_str)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&lt;', '<', clean)
    clean = re.sub(r'&gt;', '>', clean)
    clean = re.sub(r'&#\d+;', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def _get_cover_photo_url(data: Dict) -> Optional[str]:
    """Get the best available photo URL from the API response.
    
    Prefers the 'large' rendition from included pictures,
    falls back to pictureThumbnailUrl from attributes.
    """
    # Check included pictures
    included = data.get("included", [])
    pictures = [i for i in included if i.get("type") == "pictures"]
    
    # Sort by order (lowest = primary)
    pictures.sort(key=lambda p: p.get("attributes", {}).get("order", 999))
    
    for pic in pictures:
        attrs = pic.get("attributes", {})
        # Prefer large rendition
        large = attrs.get("large", {})
        if large and large.get("url"):
            return large["url"]
        original = attrs.get("original", {})
        if original and original.get("url"):
            return original["url"]
    
    # Fallback to thumbnail URL in attributes (lower quality but better than nothing)
    raw_data = data.get("data", {})
    if isinstance(raw_data, list):
        animal_data = raw_data[0] if raw_data else {}
    else:
        animal_data = raw_data
    if isinstance(animal_data, dict):
        thumb = animal_data.get("attributes", {}).get("pictureThumbnailUrl")
        if thumb:
            # Convert thumbnail URL to a larger version by adjusting width
            return re.sub(r'\?width=\d+', '?width=500', thumb)
    
    return None


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single dog profile from the RescueGroups API."""
    animal_id = target["animal_id"]
    rg_id = _extract_rg_id(animal_id)
    
    # Fetch from RescueGroups API with pictures included
    api_url = f"{API_BASE}/{rg_id}?include=pictures"
    resp = requests.get(api_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    # data can be a list (single-animal endpoint) or a dict
    raw_data = data.get("data", {})
    if isinstance(raw_data, list):
        animal_data = raw_data[0] if raw_data else {}
    else:
        animal_data = raw_data
    attrs = animal_data.get("attributes", {}) if isinstance(animal_data, dict) else {}
    
    name = (attrs.get("name") or target.get("name", "")).strip()
    gender = attrs.get("sex", target.get("gender", ""))
    age = attrs.get("ageString", target.get("age", ""))
    breed = attrs.get("breedString", "")
    
    # Weight: sizeCurrent is numeric lbs, sizeGroup is category
    size_current = attrs.get("sizeCurrent")
    size_group = attrs.get("sizeGroup", "")
    weight = f"{size_current} lbs" if size_current else size_group
    
    # Coat
    coat_length = attrs.get("coatLength", "")
    
    # Build bio from structured data + description
    bio_parts = []
    if breed:
        bio_parts.append(f"Breed: {breed}")
    if gender:
        bio_parts.append(f"Gender: {gender}")
    if age:
        bio_parts.append(f"Age: {age}")
    if weight:
        bio_parts.append(f"Weight: {weight}")
    if coat_length:
        bio_parts.append(f"Coat: {coat_length}")
    
    # Compatibility info
    compat_parts = []
    if attrs.get("isDogsOk"):
        compat_parts.append("dogs")
    if attrs.get("isCatsOk"):
        compat_parts.append("cats")
    if attrs.get("isKidsOk"):
        compat_parts.append("kids")
    if compat_parts:
        bio_parts.append(f"Good with: {', '.join(compat_parts)}")
    
    # Narrative bio from description
    narrative = _clean_html(attrs.get("descriptionHtml", ""))
    if not narrative:
        narrative = (attrs.get("descriptionText") or "").strip()
    if narrative:
        bio_parts.append("")
        bio_parts.append(narrative)
    
    bio = "\n".join(bio_parts)
    
    # Get photo URL
    image_url = _get_cover_photo_url(data)
    
    return {
        "shelter_profile_url": url,
        "animal_id": animal_id,
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
