"""
DPA (Dallas Pets Alive) — Profile Scraper

Fetches individual dog profile pages and extracts bio content.
Each profile page is a WordPress/Elementor page with structured fields
(age, breed, gender, location) and a narrative bio.

No Playwright needed — all content is in the static HTML.
Runs via Vercel crons using the shared profiles_runner.
"""

import logging
import re
import sys
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "DPA"
SHELTER_NAME = "Dallas Pets Alive"
CITY = "Dallas"
STATE = "TX"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_og_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract og:image URL from meta tags."""
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        url = meta["content"]
        if "logo" not in url.lower():
            return url
    return None


def _extract_structured_fields(text_lines: list) -> Dict[str, Optional[str]]:
    """Extract structured fields (Age, Breed, Gender, Location) from page text."""
    fields = {"age": None, "breed": None, "gender": None, "weight": None}
    
    for line in text_lines:
        line = line.strip()
        
        if line.startswith("Age:"):
            fields["age"] = line.replace("Age:", "").strip()
        elif line.startswith("Breed:"):
            fields["breed"] = line.replace("Breed:", "").strip()
        elif line.startswith("Gender:"):
            raw = line.replace("Gender:", "").strip()
            if raw.lower() in ("female", "f"):
                fields["gender"] = "Female"
            elif raw.lower() in ("male", "m"):
                fields["gender"] = "Male"
            else:
                fields["gender"] = raw
        elif line.startswith("Weight:"):
            fields["weight"] = line.replace("Weight:", "").strip()
    
    return fields


def _extract_bio(soup: BeautifulSoup) -> str:
    """Extract the full bio text from the page."""
    body = soup.find("body")
    if not body:
        return ""
    
    text_lines = body.get_text(separator="\n", strip=True).split("\n")
    
    # Find the content section — starts after "Meet {name}" or structured fields
    bio_lines = []
    in_bio = False
    skip_patterns = [
        r"^Menu$", r"^Close$", r"^Home$", r"^Adopt$", r"^Foster$",
        r"^Donate$", r"^Events$", r"^About$", r"^Contact", r"^Blog",
        r"^Search$", r"^Adoptable Dogs", r"^Adoptable Cats",
        r"^How to Adopt", r"^Dallas Pets Alive",
        r"^Age:", r"^Breed:", r"^Gender:", r"^Location:",
        r"^Adopt\s", r"^©", r"^Privacy", r"^Terms",
        r"^Follow us", r"^Email:", r"^Phone:",
        r"^Facebook$", r"^Instagram$", r"^Twitter$",
        r"^Share\s", r"^Adult$", r"^Senior$", r"^Puppy$",
        r"^Young$", r"^Female$", r"^Male$",
        r"^Large$", r"^Medium$", r"^Small$",
        r"^New Digs", r"^Get Involved", r"^Programs",
        r"^DPA!", r"^Help Save",
    ]
    
    for line in text_lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        
        # Start capturing after "Meet {name}" header
        if re.match(r"^Meet\s+", line, re.I):
            in_bio = True
            bio_lines.append(line)
            continue
        
        if not in_bio:
            continue
        
        # Stop at footer/sidebar content
        if any(re.match(pat, line, re.I) for pat in skip_patterns):
            continue
        
        # Stop at "Adopt {Name}" CTA button (appears after bio)
        if re.match(r"^Adopt\s+\w", line):
            break
        
        bio_lines.append(line)
    
    return "\n".join(bio_lines)


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single dog profile page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Extract image
    image_url = _extract_og_image(soup)
    
    # Extract structured fields
    body = soup.find("body")
    text_lines = body.get_text(separator="\n", strip=True).split("\n") if body else []
    fields = _extract_structured_fields(text_lines)
    
    # Build bio (structured fields + narrative)
    bio_parts = []
    if fields["breed"]:
        bio_parts.append(f"Breed: {fields['breed']}")
    if fields["gender"]:
        bio_parts.append(f"Gender: {fields['gender']}")
    if fields["age"]:
        bio_parts.append(f"Age: {fields['age']}")
    if fields["weight"]:
        bio_parts.append(f"Weight: {fields['weight']}")
    
    narrative = _extract_bio(soup)
    if narrative:
        bio_parts.append("")
        bio_parts.append(narrative)
    
    bio = "\n".join(bio_parts)
    
    # Extract name from title
    title_tag = soup.find("title")
    name = target.get("name", "")
    if title_tag:
        raw_title = title_tag.get_text()
        # Clean "Luna Bell - Dallas Pets Alive!" → "Luna Bell"
        name = re.sub(r'\s*[-–—]\s*Dallas Pets Alive.*$', '', raw_title).strip()
    
    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name,
        "gender": fields["gender"] or target.get("gender", ""),
        "age": fields["age"] or target.get("age", ""),
        "weight": fields["weight"] or "",
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
