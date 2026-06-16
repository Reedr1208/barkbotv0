"""
PHP (Philly PAWS) — Profile Scraper

Fetches detailed profiles from Shelterluv embed pages and upserts them
into the animals table via the shared profiles runner.

Shelterluv profile pages embed all animal data as structured JSON in the
:animal attribute of the <iframe-animal> Vue component, so no Playwright
is needed — plain HTTP requests suffice.
"""

import html
import json
import re
from typing import Any, Dict, Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape

SHELTER_ID = "PHP"
SHELTERLUV_PREFIX = "PHLP"
SHELTER_NAME = "Philly PAWS"
CITY = "Philadelphia"
STATE = "PA"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _parse_shelterluv_json(raw_html: str, attr_name: str) -> Optional[Dict[str, Any]]:
    """Extract and parse a JSON object from a Vue component attribute in Shelterluv HTML.

    Shelterluv encodes the attribute value with HTML entities:
    - Structural JSON quotes become &quot;
    - Actual quote characters INSIDE string values become &amp;quot;
    We must decode these in the right order to get valid JSON.
    """
    # Extract the raw attribute value using regex on the raw HTML
    # This avoids BeautifulSoup's auto-decoding which merges structural and inner quotes
    pattern = rf':{attr_name}="(\{{.*?\}})"'
    match = re.search(pattern, raw_html, re.S)
    if not match:
        return None

    attr_val = match.group(1)

    # Step 1: Replace double-encoded entities (inner quotes within string values)
    # &amp;quot; → escaped quote for JSON
    # &amp;amp; → & 
    # &amp;#039; → '
    attr_val = attr_val.replace("&amp;quot;", '\\"')
    attr_val = attr_val.replace("&amp;amp;", "&amp;")
    attr_val = attr_val.replace("&amp;#039;", "'")
    attr_val = attr_val.replace("&amp;", "&")

    # Step 2: Replace structural entity-encoded quotes with real quotes
    attr_val = attr_val.replace("&quot;", '"')

    try:
        return json.loads(attr_val)
    except (json.JSONDecodeError, TypeError):
        return None



def _extract_og_image(raw_html: str) -> Optional[str]:
    """Extract og:image URL from meta tags."""
    soup = BeautifulSoup(raw_html, "html.parser")
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        return meta["content"]
    return None


def _clean_bio(kennel_desc: str) -> str:
    """Clean up Shelterluv kennel_description HTML into readable text."""
    if not kennel_desc:
        return ""
    # Replace <br /> and <br> with newlines
    text = re.sub(r"<br\s*/?>", "\n", kennel_desc, flags=re.I)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_age(animal_data: Dict[str, Any]) -> str:
    """Extract human-readable age from Shelterluv animal data."""
    age_group = animal_data.get("age_group")
    if isinstance(age_group, dict):
        return age_group.get("name", "")
    return ""


def _format_weight(animal_data: Dict[str, Any]) -> str:
    """Extract weight string from Shelterluv animal data."""
    weight = animal_data.get("weight")
    units = animal_data.get("weight_units", "lbs")
    if weight:
        return f"{weight} {units}"
    return ""


def _build_bio(animal_data: Dict[str, Any]) -> str:
    """Build the bio from all available Shelterluv fields."""
    sections = []

    # Breed info
    breed = animal_data.get("breed", "")
    secondary_breed = animal_data.get("secondary_breed", "")
    if breed:
        breed_str = breed
        if secondary_breed:
            breed_str += f" / {secondary_breed}"
        sections.append(f"Breed: {breed_str}")

    # Color
    color = animal_data.get("primary_color", "")
    if color:
        sections.append(f"Color: {color}")

    # Location within shelter
    location = animal_data.get("location", "")
    if location:
        sections.append(f"Location: {location}")

    # Weight group
    weight_group = animal_data.get("weight_group", "")
    if weight_group:
        sections.append(f"Size: {weight_group}")

    # Attributes (e.g., "Featured Pet")
    attributes = animal_data.get("attributes", [])
    if attributes:
        sections.append(f"Attributes: {', '.join(attributes)}")

    # Main bio from kennel_description
    kennel_desc = animal_data.get("kennel_description", "")
    bio_text = _clean_bio(kennel_desc)
    if bio_text:
        sections.append(bio_text)

    return "\n\n".join(sections)


def fetch_record(url: str, target: dict) -> Dict[str, Any]:
    """Fetch a Shelterluv profile page and extract the record."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    raw_html = response.text

    # Extract structured animal data from the Vue component attribute
    animal_data = _parse_shelterluv_json(raw_html, "animal") or {}

    # Get the og:image for the highest quality photo
    og_image = _extract_og_image(raw_html)

    # Also try to get images from the embedded JSON
    photos = animal_data.get("photos", {})
    shelter_image_url = og_image
    if not shelter_image_url and photos:
        # Get the first photo URL from the ordered photos dict
        first_photo = next(iter(photos.values()), None)
        if isinstance(first_photo, dict):
            shelter_image_url = first_photo.get("url", "")

    # Build fields
    name = animal_data.get("name", "") or target.get("name", "")
    sex = animal_data.get("sex", "") or target.get("gender", "")
    age = _format_age(animal_data) or target.get("age", "")
    weight = _format_weight(animal_data)
    bio = _build_bio(animal_data)

    # Extract animal_id
    unique_id = animal_data.get("uniqueId", "")
    if unique_id:
        # uniqueId is like PHLP-A-181074 → extract numeric part
        numeric_match = re.search(r"(\d+)$", unique_id)
        numeric_id = numeric_match.group(1) if numeric_match else unique_id
        animal_id = f"{SHELTER_ID}-{numeric_id}"
    else:
        animal_id = target.get("animal_id", "")

    # Build more_info from shelter description
    shelter_data = _parse_shelterluv_json(raw_html, "shelter") or {}
    shelter_desc = shelter_data.get("description", "")
    more_info = shelter_desc if shelter_desc else ""

    # Check species to filter non-dogs
    species = animal_data.get("species", "").lower()
    if species and species != "dog":
        raise ValueError("NOT_A_DOG")

    return {
        "shelter_profile_url": url,
        "animal_id": animal_id,
        "name": name,
        "shelter_name": SHELTER_NAME,
        "weight": weight,
        "age": age,
        "gender": sex,
        "more_info": more_info,
        "bio": bio,
        "shelter_image_url": shelter_image_url,
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def fallback_url(animal_id: str) -> str:
    """Generate Shelterluv profile URL from our animal_id."""
    numeric_id = animal_id.replace(f"{SHELTER_ID}-", "")
    return f"https://new.shelterluv.com/embed/animal/{SHELTERLUV_PREFIX}-A-{numeric_id}"


def on_http_error(store, target, exc):
    """Handle HTTP errors — remove adopted dogs from active_dogs."""
    aid = target.get("animal_id", "")
    url = target.get("url", "")
    if hasattr(exc, "response") and exc.response is not None and exc.response.status_code in (404, 410):
        try:
            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
            print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_due_to_http_error", "status_code": exc.response.status_code}))
        except Exception as del_exc:
            import sys
            print(json.dumps({"url": url, "error": f"Failed to delete after HTTP {exc.response.status_code}: {str(del_exc)}"}), file=sys.stderr)
    import sys
    print(json.dumps({"url": url, "error": str(exc)}), file=sys.stderr)


def main() -> int:
    return run_profiles_scrape(
        shelter_id=SHELTER_ID,
        fetch_record_fn=fetch_record,
        fallback_url_fn=fallback_url,
        headers=HEADERS,
        on_http_error=on_http_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
