"""
MCACC (Maricopa County Animal Care and Control) — Profile Scraper

Fetches detailed profiles from the Maricopa County shelter detail pages
and upserts them into the animals table via the shared profiles runner.

Detail page endpoint:
  GET https://apps.pets.maricopa.gov/adoptPets/Home/Details/{animalId}
  Returns: Full HTML page with structured data sections:
    - Name, Animal ID, Breed, Age, Sex, Weight, Arrival date
    - About me (main bio)
    - Requirements, Recommendations
    - Evaluation Comments (multiple dated entries from staff/volunteers)
    - Intake Notes

All data is server-rendered HTML — no Playwright needed.

Note: Animal photos are embedded as base64 data URIs in the HTML.
      We decode and upload these directly to Supabase storage.
"""

import base64
import json
import re
import sys
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape
from jobs.lib.db import get_supabase_client
from jobs.lib.store import get_settings

SHELTER_ID = "MCACC"
SHELTER_NAME = "Maricopa County Animal Care and Control"
CITY = "Phoenix"
STATE = "AZ"

DETAIL_URL_TEMPLATE = "https://apps.pets.maricopa.gov/adoptPets/Home/Details/{raw_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _extract_base64_image(soup: BeautifulSoup) -> tuple[Optional[bytes], str]:
    """Extract and decode the base64-encoded animal photo.

    Returns (image_bytes, content_type) or (None, "") if not found.
    The Maricopa site embeds photos as data URIs like:
      data:image/gif;base64,/9j/4AAQ...
    (Despite saying gif, the actual data is JPEG based on the /9j/ header)
    """
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src.startswith("data:image"):
            continue

        # Parse data URI: data:image/type;base64,DATA
        m = re.match(r"data:image/(\w+);base64,(.+)", src, re.S)
        if not m:
            continue

        declared_type = m.group(1)
        b64_data = m.group(2)

        try:
            image_bytes = base64.b64decode(b64_data)
        except Exception:
            continue

        # Detect actual format from magic bytes
        if image_bytes[:2] == b'\xff\xd8':
            content_type = "image/jpeg"
            ext = ".jpg"
        elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = "image/png"
            ext = ".png"
        elif image_bytes[:4] == b'GIF8':
            content_type = "image/gif"
            ext = ".gif"
        else:
            content_type = f"image/{declared_type}"
            ext = f".{declared_type}"

        return image_bytes, content_type

    return None, ""


def _upload_base64_image(animal_id: str, image_bytes: bytes, content_type: str) -> tuple[Optional[str], Optional[str]]:
    """Upload decoded image bytes to Supabase storage."""
    try:
        settings = get_settings()
        client = get_supabase_client()

        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif"}
        ext = ext_map.get(content_type, ".jpg")
        object_path = f"animals/{animal_id}{ext}"

        client.storage.from_(settings.supabase_bucket).upload(
            object_path,
            image_bytes,
            file_options={
                "upsert": "true",
                "content-type": content_type,
            },
        )
        public_url = client.storage.from_(settings.supabase_bucket).get_public_url(object_path)
        return object_path, public_url
    except Exception as e:
        print(f"Failed to upload base64 image for {animal_id}: {e}", file=sys.stderr)
        return None, None


def _extract_evaluation_comments(soup: BeautifulSoup) -> str:
    """Extract all evaluation comments with dates.

    The HTML structure is:
      <div class="card-header">Evaluation Comments - ...</div>
      <div class="card-body">
        <table><tbody id="linkify">
          <tr><td>
            <span class="fw-bold d-block"> 06/12/2026</span>
            <span>Comment text...</span>
          </td></tr>
          ...
        </tbody></table>
      </div>
    """
    comments = []

    # Find the card-header containing "evaluation comment"
    for header in soup.find_all("div", class_="card-header"):
        if "evaluation comment" not in header.get_text(strip=True).lower():
            continue

        # The card-body with the table follows the header
        card = header.parent
        if not card:
            continue

        # Find all table rows in this card
        for tr in card.find_all("tr"):
            td = tr.find("td")
            if not td:
                continue

            # Date is in a bold span
            date_span = td.find("span", class_="fw-bold")
            date = date_span.get_text(strip=True) if date_span else ""

            # Comment is in the next span(s)
            comment_parts = []
            for span in td.find_all("span"):
                if span == date_span:
                    continue
                text = span.get_text(strip=True)
                if text:
                    comment_parts.append(text)

            comment = " ".join(comment_parts)
            if date and comment:
                comments.append(f"[{date}] {comment}")

        break

    return "\n\n".join(comments)


def _extract_intake_notes(soup: BeautifulSoup) -> str:
    """Extract intake notes section (same table structure as eval comments)."""
    notes = []

    for header in soup.find_all("div", class_="card-header"):
        if "intake note" not in header.get_text(strip=True).lower():
            continue

        card = header.parent
        if not card:
            continue

        for tr in card.find_all("tr"):
            td = tr.find("td")
            if not td:
                continue

            date_span = td.find("span", class_="fw-bold")
            date = date_span.get_text(strip=True) if date_span else ""

            note_parts = []
            for span in td.find_all("span"):
                if span == date_span:
                    continue
                text = span.get_text(strip=True)
                if text:
                    note_parts.append(text)

            note = " ".join(note_parts)
            if date and note:
                notes.append(f"[{date}] {note}")

        break

    return "\n\n".join(notes)


def _extract_section_items(soup: BeautifulSoup, section_name: str) -> str:
    """Extract items from a card section (Requirements, Recommendations).

    Recommendations use: card-header > card-body > row > col (one item per col)
    Requirements use: card-header > card-body > span
    """
    for header in soup.find_all("div", class_="card-header"):
        header_text = header.get_text(strip=True).lower()
        # Match "requirements" or "recommendations" header
        if section_name.lower() not in header_text:
            continue
        # Avoid matching "evaluation comments" when looking for just "comment"
        if "evaluation" in header_text and "evaluation" not in section_name.lower():
            continue

        card = header.parent
        if not card:
            continue

        body = card.find("div", class_="card-body")
        if not body:
            continue

        # Try extracting from col divs (recommendations style)
        cols = body.find_all("div", class_="col")
        if cols:
            items = [col.get_text(strip=True) for col in cols if col.get_text(strip=True)]
            if items:
                return ", ".join(items)

        # Fall back to span text (requirements style)
        spans = body.find_all("span")
        if spans:
            items = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
            if items:
                return ", ".join(items)

        # Fall back to all text in the body
        text = body.get_text(strip=True)
        return text if text else ""

    return ""


def fetch_record(url: str, target: dict) -> Dict[str, Any]:
    """Fetch a Maricopa detail page and extract the full record."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    raw_html = response.text
    soup = BeautifulSoup(raw_html, "html.parser")

    full_text = soup.get_text()

    # ── Name ──────────────────────────────────────────────────────────
    name = ""
    m = re.search(r"Name\s+([A-Z][A-Z\s]+?)(?:\s+Animal ID)", full_text, re.S)
    if m:
        name = m.group(1).strip().title()
    if not name:
        name = target.get("name", "")

    # ── Animal ID ─────────────────────────────────────────────────────
    raw_id = ""
    m = re.search(r"Animal ID\s+(A\d+)", full_text)
    if m:
        raw_id = m.group(1)
    if not raw_id:
        m = re.search(r"/Details/(A\d+)", url)
        if m:
            raw_id = m.group(1)

    animal_id = f"{SHELTER_ID}-{raw_id.lstrip('A')}" if raw_id else target.get("animal_id", "")

    # ── Breed ─────────────────────────────────────────────────────────
    breed = ""
    m = re.search(r"Breed\s+(.+?)(?:\s+Age\b)", full_text, re.S)
    if m:
        breed = m.group(1).strip()

    # ── Age ───────────────────────────────────────────────────────────
    age = ""
    m = re.search(r"Age\s+(.+?)(?:\s+Sex\b)", full_text, re.S)
    if m:
        age = m.group(1).strip()
    if not age:
        age = target.get("age", "")

    # ── Gender ────────────────────────────────────────────────────────
    gender = ""
    m = re.search(r"Sex\s+(Male|Female)", full_text, re.I)
    if m:
        gender = m.group(1)
    if not gender:
        gender = target.get("gender", "")

    # ── Weight ────────────────────────────────────────────────────────
    weight = ""
    m = re.search(r"Weight\s+(\d+)", full_text)
    if m:
        weight = f"{m.group(1)} lbs"

    # ── About me (main bio) ──────────────────────────────────────────
    about_me = ""
    m = re.search(r"About me\s+(.+?)(?:\s+Requirement)", full_text, re.S)
    if m:
        about_me = m.group(1).strip()

    # ── Recommendations ──────────────────────────────────────────────
    recommendations = _extract_section_items(soup, "Recommendation")

    # ── Requirements ─────────────────────────────────────────────────
    requirements = _extract_section_items(soup, "Requirement")

    # ── Evaluation Comments ──────────────────────────────────────────
    eval_comments = _extract_evaluation_comments(soup)

    # ── Intake Notes ─────────────────────────────────────────────────
    intake_notes = _extract_intake_notes(soup)

    # ── Image (base64 embedded) ──────────────────────────────────────
    image_bytes, content_type = _extract_base64_image(soup)
    image_file = None
    image_public_url = None
    if image_bytes:
        image_file, image_public_url = _upload_base64_image(animal_id, image_bytes, content_type)

    # ── Build comprehensive bio ──────────────────────────────────────
    bio_sections = []

    if breed:
        bio_sections.append(f"Breed: {breed}")

    if about_me:
        bio_sections.append(f"About me: {about_me}")

    if recommendations:
        bio_sections.append(f"Recommendations: {recommendations}")

    if requirements and requirements.lower() not in ("no requirements", ""):
        bio_sections.append(f"Requirements: {requirements}")

    if eval_comments:
        bio_sections.append(f"Evaluation Comments:\n{eval_comments}")

    if intake_notes:
        bio_sections.append(f"Intake Notes:\n{intake_notes}")

    bio = "\n\n".join(bio_sections)

    # ── Adoption fee ─────────────────────────────────────────────────
    more_info = ""
    m = re.search(r"Adoption fee\s+(.+?)(?:\s+Breed\b)", full_text, re.S)
    if m:
        more_info = f"Adoption fee: {m.group(1).strip()}"

    return {
        "shelter_profile_url": url,
        "animal_id": animal_id,
        "name": name,
        "shelter_name": SHELTER_NAME,
        "weight": weight,
        "age": age,
        "gender": gender,
        "more_info": more_info,
        "bio": bio,
        "shelter_image_url": "",  # No external URL; image uploaded from base64
        "image_file": image_file,
        "image_public_url": image_public_url,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def fallback_url(animal_id: str) -> str:
    """Generate Maricopa detail URL from our animal_id."""
    numeric_id = animal_id.replace(f"{SHELTER_ID}-", "")
    return DETAIL_URL_TEMPLATE.format(raw_id=f"A{numeric_id}")


def on_http_error(store, target, exc):
    """Handle HTTP errors — remove adopted/unavailable dogs from active_dogs."""
    aid = target.get("animal_id", "")
    url = target.get("url", "")
    if hasattr(exc, "response") and exc.response is not None and exc.response.status_code in (404, 410):
        try:
            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
            print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_due_to_http_error", "status_code": exc.response.status_code}))
        except Exception as del_exc:
            print(json.dumps({"url": url, "error": f"Failed to delete after HTTP {exc.response.status_code}: {str(del_exc)}"}), file=sys.stderr)
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
