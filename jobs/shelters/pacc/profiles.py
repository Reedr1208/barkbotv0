"""
PACC (Pima Animal Care Center) — Profile Scraper

Fetches detailed profiles from 24petconnect.com for PACC dogs
and upserts them into the animals table.
"""

import hashlib
import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def get_animal_id_from_url(url: str) -> str:
    match = re.search(r"/(A\d+)$", url)
    return match.group(1) if match else hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def text_or_none(node: Any) -> Optional[str]:
    if not node:
        return None
    text = node.get_text("\n", strip=True)
    return text if text else None


def extract_image_url(soup: BeautifulSoup) -> Optional[str]:
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image and og_image.get("content"):
        return og_image["content"].strip()

    full_img = soup.select_one("#FullImage")
    if full_img and full_img.get("src"):
        return urljoin("https://24petconnect.com", full_img["src"].strip())

    thumb = soup.select_one("#PictureBoxThumbs img")
    if thumb and thumb.get("src"):
        return urljoin("https://24petconnect.com", thumb["src"].strip())

    return None


def extract_profile_from_html(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    native_id = get_animal_id_from_url(url)
    animal_id = f"PACC-{native_id}"

    description_node = soup.select_one("span.text_Description.details")
    weight_node = soup.select_one("span.text_Weight.details")
    age_node = soup.select_one("span.text_Age.details")
    more_info_node = soup.select_one("span.text_MoreInfo.details")
    bio_node = soup.select_one("div.line_Bio.details span.text_Bio.details")

    image_url = extract_image_url(soup)

    desc_text = text_or_none(description_node)
    bio_text = text_or_none(bio_node)

    merged_bio = ""
    if desc_text:
        merged_bio += desc_text + "\n\n"
    if bio_text:
        merged_bio += bio_text
    merged_bio = merged_bio.strip()

    return {
        "shelter_profile_url": url,
        "animal_id": animal_id,
        "shelter_name": "Pima Animal Care Center",
        "weight": text_or_none(weight_node),
        "age": text_or_none(age_node),
        "more_info": text_or_none(more_info_node),
        "bio": merged_bio,
        "shelter_image_url": image_url,
        "image_file": None,
        "image_public_url": None,
        "city": "Tucson",
        "state": "AZ",
        "shelter_id": "PACC"
    }


def fetch_record(url: str, target: dict) -> Dict[str, Any]:
    """
    Fetch a PACC profile. Tries the primary URL, then falls back to
    an alternate EPAC URL if the primary returns a 404/500.
    """
    native_id = get_animal_id_from_url(url)

    urls_to_try = [
        url,
        f"https://24petconnect.com/AdoptEPAC/Details/PIMA2/{native_id}"
    ]

    last_exc = None
    for try_url in urls_to_try:
        try:
            response = requests.get(try_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            record = extract_profile_from_html(response.text, try_url)
            record["name"] = target.get("name")
            record["gender"] = target.get("gender")
            return record
        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code in (404, 500):
                last_exc = exc
                continue
            raise
        except Exception:
            last_exc = None
            raise

    # All URLs failed
    if last_exc:
        raise last_exc
    raise RuntimeError(f"All URLs failed for PACC-{native_id}")


def fallback_url(animal_id: str) -> str:
    native_id = animal_id.replace("PACC-", "")
    return f"https://24petconnect.com/PimaAdoptablePets/Details/PIMA/{native_id}"


def main() -> int:
    return run_profiles_scrape(
        shelter_id="PACC",
        fetch_record_fn=fetch_record,
        fallback_url_fn=fallback_url,
        headers=HEADERS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
