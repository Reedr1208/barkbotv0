"""
EHR (Eleventh Hour Rescue) — Profile Scraper

Fetches individual dog profile pages from ehrdogs.org (Buzz Rescues
WordPress theme) and extracts structured fields + bio text.

The detail pages (e.g. /dog/alvin-dixon/) contain:
- Title: Dog name in <h2 class="Bzl-dog-title">
- Main photo and gallery thumbnails
- Bio text in <div class="dog-description">
- Structured features in <li class="features_item"> elements with icons
  for Breed, Age, Weight, Color, Energy Level, Kids, Dogs, Cats, etc.

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

# Icon class -> field name mapping for structured features
ICON_FIELD_MAP = {
    "icon-dog-face": None,   # context-dependent: Breed or Good With Dogs
    "icon-cake": "age",
    "icon-weight-machine": "weight",
    "icon-color-palette": "color",
    "icon-energy": "energy_level",
    "icon-child": "good_with_kids",
    "icon-cat-face": "good_with_cats",
    "icon-other-animal": "small_animals",
    "icon-info": "livestock",
    "icon-accountant": "adoption_fee",
    "icon-male-sign": "gender",
    "icon-female-sign": "gender",
}


def _extract_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main dog photo URL from the Buzz Rescues detail page.

    The main image is inside <div class="Bzl-dog-img"> → <a class="dogPics"> → <img>.
    The <a> href points to the full-resolution image.
    """
    gallery = soup.find("div", class_="Bzl-dog-single-gallery")
    if not gallery:
        gallery = soup.find("div", class_="Bzl-popup-gallery")

    if gallery:
        # Primary image: the main <a class="dogPics"> in Bzl-dog-img
        dog_img_div = gallery.find("div", class_="Bzl-dog-img")
        if dog_img_div:
            main_link = dog_img_div.find("a", class_="dogPics")
            if main_link and main_link.get("href"):
                return main_link["href"]
            # Fallback: the img src
            img = dog_img_div.find("img")
            if img:
                src = img.get("src", "")
                if src and not src.startswith("data:"):
                    if src.startswith("/"):
                        return f"https://ehrdogs.org{src}"
                    return src

    # Fallback: og:image meta tag
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        return og_img["content"]

    return None


def _extract_name(soup: BeautifulSoup) -> str:
    """Extract the dog's name from the page."""
    # Try og:title first (cleanest)
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        name = og_title["content"].strip()
        if name and name != "Eleventh Hour Rescue":
            return name

    # Try the Bzl-dog-title heading
    title_h2 = soup.find("h2", class_="Bzl-dog-title")
    if title_h2:
        strong = title_h2.find("strong")
        if strong:
            return strong.get_text(strip=True)
        return title_h2.get_text(strip=True)

    # Fallback: page <title>
    title_tag = soup.find("title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        # Format: "Dog Name – Eleventh Hour Rescue"
        name = re.split(r"\s*[–—-]\s*Eleventh Hour", raw)[0].strip()
        if name:
            return name

    return ""


def _extract_features(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract structured feature fields from the detail page.

    Features are in <li class="features_item"> elements, each containing
    an icon <i> and the field text.
    """
    features = {}

    # Find the info section
    info_section = soup.find("div", class_="Bzl-dog-single-info")
    if not info_section:
        info_section = soup  # Fallback to whole page

    breed_count = 0
    for item in info_section.find_all("li", class_="features_item"):
        icon = item.find("i", class_="icon")
        if not icon:
            continue

        icon_classes = " ".join(icon.get("class", []))
        icon_title = (icon.get("title") or "").strip()
        text = item.get_text(strip=True)

        # Determine field based on icon class and title
        if "icon-dog-face" in icon_classes:
            if icon_title == "Breed":
                features["breed"] = text
                breed_count += 1
            elif "Good With Dogs" in icon_title:
                features["good_with_dogs"] = text
            else:
                # If we haven't seen a breed yet, treat as breed
                if breed_count == 0:
                    features["breed"] = text
                    breed_count += 1
                else:
                    features["good_with_dogs"] = text
        elif "icon-cake" in icon_classes:
            # Extract DOB from <small> tag before getting age text
            small = item.find("small")
            if small:
                dob_match = re.search(r"(\d{2}/\d{2}/\d{4})", small.get_text())
                if dob_match:
                    features["dob"] = dob_match.group(1)
                # Remove the small tag so it doesn't pollute age text
                small.decompose()
            features["age"] = item.get_text(strip=True)
        elif "icon-weight-machine" in icon_classes:
            features["weight"] = text
        elif "icon-color-palette" in icon_classes:
            features["color"] = text
        elif "icon-energy" in icon_classes:
            features["energy_level"] = text
        elif "icon-child" in icon_classes:
            features["good_with_kids"] = text
        elif "icon-cat-face" in icon_classes:
            features["good_with_cats"] = text
        elif "icon-male-sign" in icon_classes or "icon-female-sign" in icon_classes:
            if "icon-female-sign" in icon_classes:
                features["gender"] = "Female"
            else:
                features["gender"] = "Male"
        elif "icon-accountant" in icon_classes:
            features["adoption_fee"] = text

    return features


def _extract_bio(soup: BeautifulSoup) -> str:
    """Extract the narrative bio text from the dog-description div."""
    desc_div = soup.find("div", class_="dog-description")
    if not desc_div:
        return ""

    paragraphs = []
    for p in desc_div.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)


def _is_catch_all_tile(name: str) -> bool:
    """Check if this is a catch-all tile (generic application entry)."""
    return name.startswith("*") or name.startswith("**")


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single Buzz Rescues dog detail page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract name
    name = _extract_name(soup)

    # Check for catch-all tiles
    if _is_catch_all_tile(name):
        raise ValueError("NOT_A_DOG")

    # Extract structured features
    features = _extract_features(soup)

    # Extract bio narrative
    narrative = _extract_bio(soup)

    # Build bio with structured fields + narrative
    bio_parts = []

    breed = features.get("breed", "")
    if breed:
        bio_parts.append(f"Breed: {breed}")

    gender = features.get("gender", "")
    if gender:
        bio_parts.append(f"Gender: {gender}")

    age = features.get("age", "")
    if age:
        bio_parts.append(f"Age: {age}")

    weight = features.get("weight", "")
    if weight:
        bio_parts.append(f"Weight: {weight}")

    color = features.get("color", "")
    if color:
        bio_parts.append(f"Color: {color}")

    energy = features.get("energy_level", "")
    if energy:
        bio_parts.append(f"Energy Level: {energy}")

    good_with_kids = features.get("good_with_kids", "")
    if good_with_kids:
        bio_parts.append(f"Good with kids: {good_with_kids}")

    good_with_dogs = features.get("good_with_dogs", "")
    if good_with_dogs:
        bio_parts.append(f"Good with dogs: {good_with_dogs}")

    good_with_cats = features.get("good_with_cats", "")
    if good_with_cats:
        bio_parts.append(f"Good with cats: {good_with_cats}")

    if narrative:
        bio_parts.append("")
        bio_parts.append(narrative)

    bio = "\n".join(bio_parts)

    image_url = _extract_image(soup)

    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name or target.get("name", ""),
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
