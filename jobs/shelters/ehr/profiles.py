"""
EHR (Eleventh Hour Rescue) — Profile Scraper

Fetches individual dog profile pages from ehrdogs.org (RescueGroups)
and extracts structured fields + bio text.

The detail pages contain:
- Header: "Breed / Mixed  ::  Gender (spayed/neutered)  ::  Age  ::  Size"
- Structured table: Status, Species, Color, Size, Age, Housetrained, etc.
- Narrative bio text
- Multiple photos from cdn.rescuegroups.org

No Playwright needed — all static HTML. Runs via Vercel crons.
"""

import logging
import re
import sys
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "EHR"
SHELTER_NAME = "Eleventh Hour Rescue"
CITY = "Dover"
STATE = "NJ"

# Catch-all tile IDs to skip
EXCLUDED_IDS = {"22543099", "22543103"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main dog photo URL from RescueGroups CDN."""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "cdn.rescuegroups.org" in src and "width=500" in src:
            return src
    # Fallback: any rescuegroups image
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "cdn.rescuegroups.org" in src and "/pictures/animals/" in src:
            return re.sub(r"\?width=\d+", "?width=500", src)
    return None


def _parse_header_line(text_lines: list) -> Dict[str, str]:
    """Parse the header line like 'Terrier / Mixed (short coat)  ::  Male (neutered)  ::  Adult  ::  Medium'."""
    fields = {"breed": "", "gender": "", "age": "", "size": ""}
    
    for line in text_lines:
        if "  : :  " in line or " :: " in line:
            parts = re.split(r"\s*::\s*|\s*: :\s*", line)
            if len(parts) >= 1:
                fields["breed"] = parts[0].strip()
            if len(parts) >= 2:
                raw_gender = parts[1].strip()
                if "female" in raw_gender.lower():
                    fields["gender"] = "Female"
                elif "male" in raw_gender.lower():
                    fields["gender"] = "Male"
                else:
                    fields["gender"] = raw_gender
            if len(parts) >= 3:
                fields["age"] = parts[2].strip()
            if len(parts) >= 4:
                fields["size"] = parts[3].strip()
            break
    
    return fields


def _parse_structured_fields(text_lines: list) -> Dict[str, str]:
    """Parse structured fields from the 'About' table section."""
    fields = {}
    field_labels = [
        "Status", "Species", "General Color", "Color", "Current Size",
        "Current Age", "Microchipped", "Housetrained",
        "Obedience Training Needed", "Exercise Needs",
        "Owner Experience Needed", "Adoption Fee",
    ]
    
    for i, line in enumerate(text_lines):
        clean = line.lstrip(": ").strip()
        for label in field_labels:
            if clean == label and i + 1 < len(text_lines):
                val = text_lines[i + 1].lstrip(": ").strip()
                if val and val not in field_labels:
                    fields[label] = val
                break
    
    return fields


def _extract_bio(text_lines: list, name: str) -> str:
    """Extract the narrative bio text."""
    bio_lines = []
    in_bio = False
    
    skip_patterns = [
        r"^HELP CELEBRATE", r"^DONATE", r"^Facebook", r"^TikTok",
        r"^Instagram", r"^Animal Browse", r"^Review our",
        r"^Adoption Application", r"^ADVANCED SEARCH",
        r"^Scroll down", r"^More Pics", r"^Interested in",
        r"^adopting$", r"^Sponsor This Pet", r"^About\s",
        r"^Status$", r"^Species$", r"^General Color$",
        r"^Color$", r"^Current Size$", r"^Current Age$",
        r"^Microchipped$", r"^Housetrained$",
        r"^Obedience Training", r"^Exercise Needs",
        r"^Owner Experience", r"^Adoption Fee",
        r"^More about\s", r"^Is Not Good", r"^Good with",
        r"^Is Good with", r"^Not Good with",
        r"^Lived with", r"^Not Lived with",
        r"^Prefers a home", r"^Needs a yard",
        r"^Click for more", r"^\{s956",
        r"^Available for Adoption", r"^adoption info",
        r"^BACK to browse", r"^Back to browse",
        r"^\*\*A Puppy", r"^\*A Dog 7",
        r"^addthis_", r"^Please$",
    ]
    
    # Find the main bio content — usually after "About {Name}" header
    # or after the structured fields section
    for i, line in enumerate(text_lines):
        line = line.strip()
        if not line:
            continue
        
        # Start capturing after structured fields end
        # Bio typically starts with a paragraph about the dog
        if re.match(r"^: (High|Low|Medium|Species|Yes|No|None)", line):
            continue
        
        if any(re.match(pat, line, re.I) for pat in skip_patterns):
            continue
        
        # Start bio after "needs a caretaker" line or after structured section
        if "needs a caretaker" in line.lower() or "won't you consider" in line.lower():
            in_bio = True
            continue
        
        if not in_bio:
            # Check if this looks like a bio paragraph (long text, not a label)
            if len(line) > 80 and not line.startswith(":"):
                in_bio = True
                bio_lines.append(line)
            continue
        
        # Stop at footer content
        if line.startswith("More about "):
            break
        if "EHRDOGS.ORG" in line.upper():
            bio_lines.append(line)
            break
        
        if len(line) > 3 and not line.startswith(":"):
            bio_lines.append(line)
    
    return "\n".join(bio_lines)


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single RescueGroups dog detail page."""
    # Check if this is a catch-all tile
    match = re.search(r"AnimalID=(\d+)", url)
    if match and match.group(1) in EXCLUDED_IDS:
        raise ValueError("NOT_A_DOG")
    
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    text_lines = body.get_text(separator="\n", strip=True).split("\n") if body else []
    
    # Parse header line (breed :: gender :: age :: size)
    header = _parse_header_line(text_lines)
    
    # Parse structured fields
    struct = _parse_structured_fields(text_lines)
    
    # Extract name from page title
    name = target.get("name", "")
    title = soup.find("title")
    if title:
        raw = title.get_text(strip=True)
        name = re.sub(r"'s Web Page$", "", raw).strip()
    
    # Build bio
    bio_parts = []
    breed = header.get("breed", "")
    if breed:
        bio_parts.append(f"Breed: {breed}")
    gender = header.get("gender", "")
    if gender:
        bio_parts.append(f"Gender: {gender}")
    
    age = struct.get("Current Age", header.get("age", ""))
    if age:
        bio_parts.append(f"Age: {age}")
    
    size = struct.get("Current Size", header.get("size", ""))
    if size:
        bio_parts.append(f"Size: {size}")
    
    if struct.get("General Color"):
        bio_parts.append(f"Color: {struct['General Color']}")
    if struct.get("Housetrained") and struct["Housetrained"] not in ("Unknown",):
        bio_parts.append(f"Housetrained: {struct['Housetrained']}")
    
    narrative = _extract_bio(text_lines, name)
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
