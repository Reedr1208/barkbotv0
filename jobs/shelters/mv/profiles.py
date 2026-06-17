"""
MV (Muttville Senior Dog Rescue) — Profile Scraper

Fetches individual mutt profile pages from muttville.org and extracts
structured fields + bio text.

Each profile page has:
- Name and Muttville ID (#XXXXX)
- Breed
- Weight (e.g. "11 lbs (small)")
- Estimated age (e.g. "Est. age: 10 yrs")
- Status
- Narrative bio paragraph
- Photos from muttville-media CDN

No Playwright needed — all static HTML. Runs via Vercel crons.
"""

import logging
import re
import sys
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "MV"
SHELTER_NAME = "Muttville Senior Dog Rescue"
CITY = "San Francisco"
STATE = "CA"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main dog photo URL."""
    # Try og:image first
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        url = meta["content"]
        if "muttville" in url:
            return url

    # Look for muttville-media CDN images
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if "muttville-media" in src and "logo" not in src.lower():
            return src

    return None


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single Muttville mutt profile page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    text_lines = body.get_text(separator="\n", strip=True).split("\n") if body else []

    # Extract structured fields
    name = target.get("name", "")
    breed = ""
    weight = ""
    age = ""
    gender = ""
    mutt_id = ""

    for i, line in enumerate(text_lines):
        line = line.strip()

        # Name appears before the ID
        if re.match(r"^#\d+$", line):
            mutt_id = line
            # Name is the previous non-empty line
            for j in range(i - 1, -1, -1):
                prev = text_lines[j].strip()
                if prev and prev != "Mutts" and prev != "Available":
                    name = prev
                    break

        # Breed — appears after the ID, typically a breed name
        # It's the line after the ID that isn't a weight or age
        if mutt_id and not breed:
            if i > 0 and text_lines[i - 1].strip() == mutt_id:
                if not line.startswith("Est.") and "lbs" not in line and "Status" not in line:
                    breed = line

        # Weight
        if "lbs" in line and not line.startswith("Est."):
            weight = line

        # Age
        if line.startswith("Est. age:"):
            age = line.replace("Est. age:", "").strip()

        # Gender — check for Male/Female
        lower = line.lower()
        if lower in ("male", "female"):
            gender = line.title()

    # Build bio
    bio_parts = []
    if breed:
        bio_parts.append(f"Breed: {breed}")
    if gender:
        bio_parts.append(f"Gender: {gender}")
    if age:
        bio_parts.append(f"Age: {age}")
    if weight:
        bio_parts.append(f"Weight: {weight}")

    # Extract narrative bio — the longer paragraph(s) after structured fields
    narrative_lines = []
    for line in text_lines:
        line = line.strip()
        # Bio paragraphs are typically long (>80 chars) and not nav/footer
        if len(line) > 80:
            # Skip nav, footer, address lines
            skip = any(kw in line for kw in [
                "Muttville -", "750 Florida", "San Francisco, CA",
                "info@muttville", "Watch a live broadcast",
                "How to Adopt", "available_mutts", "muttville.org/mutt/",
            ])
            if not skip:
                narrative_lines.append(line)

    if narrative_lines:
        bio_parts.append("")
        bio_parts.extend(narrative_lines)

    bio = "\n".join(bio_parts)

    image_url = _extract_image(soup)

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
