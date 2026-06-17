"""
NHS (Nassau Humane Society) — Profile Scraper

Fetches individual dog profile pages from the PetPoint/Petango detail
endpoint and extracts structured fields + bio text.

No Playwright needed — all content is static HTML.
Runs via Vercel crons using the shared profiles_runner.
"""

import logging
import re
import sys
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "NHS"
SHELTER_NAME = "Nassau Humane Society"
CITY = "Jacksonville"
STATE = "FL"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_field(soup: BeautifulSoup, field_id: str) -> str:
    """Extract a field value from the Petango detail page by its label ID."""
    label = soup.find(id=field_id)
    if label:
        return label.get_text(strip=True)
    return ""


def _extract_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main dog photo URL."""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "petango.com/photos" in src or "g.petango.com" in src:
            return src
    return None


def _extract_bio(soup: BeautifulSoup) -> str:
    """Extract the bio/description text from the detail page."""
    body = soup.find("body")
    if not body:
        return ""

    text = body.get_text(separator="\n", strip=True)
    lines = text.split("\n")

    # The bio text comes after structured fields and before footer items
    bio_lines = []
    in_bio = False
    skip_patterns = [
        r"^Animal Details$", r"^Meet$", r"^Click a number",
        r"^\d+$", r"^Species$", r"^Dog$", r"^Cat$",
        r"^Breed$", r"^Age$", r"^Gender$", r"^Size$",
        r"^Color$", r"^Spayed/Neutered$", r"^Declawed$",
        r"^Housetrained$", r"^Site$", r"^Location$",
        r"^Intake Date$", r"^Adoption Price$",
        r"^Nassau Humane Society$", r"^Kennel$",
        r"^\$[\d.]+$", r"^Yes$", r"^No$", r"^Unknown$",
        r"^Male$", r"^Female$", r"^Large$", r"^Medium$", r"^Small$",
        r"^Favorite This Pet$", r"^Search More Pets$",
        r"^\d+/\d+/\d+$",  # dates
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Bio starts after "Meet {Name}" heading
        if re.match(r"^Meet\s+\w", line):
            in_bio = True
            bio_lines.append(line)
            continue

        if not in_bio:
            continue

        if any(re.match(pat, line, re.I) for pat in skip_patterns):
            continue

        if line in ("Favorite This Pet", "Search More Pets"):
            break

        bio_lines.append(line)

    return "\n".join(bio_lines)


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single Petango dog detail page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract structured fields from page text
    body = soup.find("body")
    text_lines = body.get_text(separator="\n", strip=True).split("\n") if body else []

    # Build a field map from consecutive label/value lines
    fields = {}
    field_labels = ["Species", "Breed", "Age", "Gender", "Size", "Color",
                    "Spayed/Neutered", "Housetrained", "Site", "Location",
                    "Intake Date", "Adoption Price"]
    for i, line in enumerate(text_lines):
        if line.strip() in field_labels and i + 1 < len(text_lines):
            fields[line.strip()] = text_lines[i + 1].strip()

    # Extract name from "Meet {Name}" pattern
    name = target.get("name", "")
    for line in text_lines:
        if line.strip().startswith("Meet "):
            name = line.strip().replace("Meet ", "").strip()
            break

    gender = fields.get("Gender")
    if gender:
        gender = "Female" if "female" in gender.lower() else "Male" if "male" in gender.lower() else gender

    age = fields.get("Age", "")
    breed = fields.get("Breed", "")
    size = fields.get("Size", "")

    # Build bio with structured fields + narrative
    bio_parts = []
    if breed:
        bio_parts.append(f"Breed: {breed}")
    if gender:
        bio_parts.append(f"Gender: {gender}")
    if age:
        bio_parts.append(f"Age: {age}")
    if size:
        bio_parts.append(f"Size: {size}")
    if fields.get("Color"):
        bio_parts.append(f"Color: {fields['Color']}")
    if fields.get("Spayed/Neutered") and fields["Spayed/Neutered"] not in ("No", "Unknown"):
        bio_parts.append(f"Spayed/Neutered: {fields['Spayed/Neutered']}")
    if fields.get("Housetrained") and fields["Housetrained"] != "Unknown":
        bio_parts.append(f"Housetrained: {fields['Housetrained']}")

    narrative = _extract_bio(soup)
    if narrative:
        bio_parts.append("")
        bio_parts.append(narrative)

    bio = "\n".join(bio_parts)

    image_url = _extract_image(soup)

    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name,
        "gender": gender or target.get("gender", ""),
        "age": age or target.get("age", ""),
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
