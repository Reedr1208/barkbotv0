"""
SAPA (San Antonio Pets Alive) — Profile Scraper

Scrapes detailed profiles from Shelterluv embed pages using direct HTTP
requests. Shelterluv embeds all animal data as a JSON attribute
(:animal="...") in the server-rendered HTML, so no browser is needed.
"""

import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests

from jobs.lib.db import now_iso
from jobs.lib.store import BarkbotStore, get_settings, DEFAULT_DOGS_PER_RUN as DOGS_PER_RUN


MAX_EXECUTION_TIME_SECONDS = 240  # 4 minutes

SHELTER_ID = "SAPA"
SHELTERLUV_PREFIX = "SAPA"
SHELTER_NAME = "San Antonio Pets Alive"
CITY = "San Antonio"
STATE = "TX"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

# Regex to extract the :animal JSON attribute from Shelterluv HTML
_ANIMAL_ATTR_RE = re.compile(r':animal="([^"]+)"')


def _decode_html_entities(s: str) -> str:
    """Decode the common HTML entities used by Shelterluv in attribute values."""
    return (
        s.replace("&quot;", '"')
         .replace("&amp;", "&")
         .replace("&lt;", "<")
         .replace("&gt;", ">")
         .replace("&#039;", "'")
         .replace("&apos;", "'")
    )


def fetch_shelterluv_profile(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Fetch a Shelterluv profile page and parse the :animal JSON attribute.

    Returns (animal_dict, cover_image_url) or (None, None) on failure.
    """
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    html = resp.text

    # Check for 404
    if "error_404" in html or "Page Not Found" in html:
        raise ValueError("NOT_FOUND")

    match = _ANIMAL_ATTR_RE.search(html)
    if not match:
        logging.warning(f"No :animal attribute found in {url}")
        return None, None

    raw_json = _decode_html_entities(match.group(1))

    try:
        animal = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse :animal JSON from {url}: {e}")
        return None, None

    # Determine cover image
    cover_url = None
    photos = animal.get("photos") or []
    if isinstance(photos, list):
        # Prefer the cover photo
        for photo in photos:
            if isinstance(photo, dict) and photo.get("isCover"):
                cover_url = photo.get("url")
                break
        # Fallback to first photo
        if not cover_url and photos:
            first = photos[0]
            if isinstance(first, dict):
                cover_url = first.get("url")
            elif isinstance(first, str):
                cover_url = first

    # Also check og:image as fallback
    if not cover_url:
        og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if og_match:
            cover_url = og_match.group(1)

    return animal, cover_url


def _compute_age_from_birthday(birthday_ts: str) -> str:
    """Convert a Unix timestamp birthday to a human-readable age string."""
    try:
        born = datetime.fromtimestamp(int(birthday_ts), tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - born
        years = delta.days // 365
        months = (delta.days % 365) // 30
        if years >= 1:
            return f"{years} yr" + (f", {months} mo" if months else "")
        elif months >= 1:
            return f"{months} mo"
        else:
            weeks = delta.days // 7
            return f"{weeks} wk" if weeks > 0 else f"{delta.days} day"
    except (ValueError, TypeError, OSError):
        return ""


def _build_bio(animal: Dict[str, Any]) -> str:
    """Build a structured bio string from the Shelterluv animal dict."""
    sections = []

    breed = animal.get("breed", "")
    secondary_breed = animal.get("secondary_breed", "")
    if breed:
        full_breed = breed
        if secondary_breed:
            full_breed += f" / {secondary_breed}"
        sections.append(f"Breed: {full_breed}")

    sex = animal.get("sex", "")
    if sex:
        sections.append(f"Sex: {sex}")

    weight = animal.get("weight")
    weight_units = animal.get("weight_units", "lbs")
    if weight:
        sections.append(f"Weight: {weight} {weight_units}")

    # Age from birthday timestamp or age_group
    birthday = animal.get("birthday")
    age_str = ""
    if birthday:
        age_str = _compute_age_from_birthday(str(birthday))
    if not age_str:
        age_group = animal.get("age_group")
        if isinstance(age_group, dict):
            age_str = age_group.get("name", "")
    if age_str:
        sections.append(f"Age: {age_str}")

    location = animal.get("location", "")
    if location:
        sections.append(f"Location: {location}")

    campus = animal.get("campus", "")
    if campus:
        sections.append(f"Campus: {campus}")

    # Main description / kennel notes
    kennel_desc = animal.get("kennel_description", "")
    if kennel_desc:
        # Clean up HTML tags
        clean_desc = re.sub(r"<br\s*/?>", "\n", kennel_desc)
        clean_desc = re.sub(r"<[^>]+>", "", clean_desc)
        clean_desc = clean_desc.strip()
        if clean_desc:
            sections.append(clean_desc)

    # Attributes (e.g. "4. Foster Home")
    attributes = animal.get("attributes") or []
    if isinstance(attributes, list) and attributes:
        attrs_str = ", ".join(str(a) for a in attributes)
        sections.append(f"Attributes: {attrs_str}")

    return "\n\n".join(sections)


def _normalize_weight(animal: Dict[str, Any]) -> str:
    """Extract and normalize weight string."""
    weight = animal.get("weight")
    if not weight:
        return ""
    units = animal.get("weight_units", "lbs")
    return f"{weight} {units}"


def _normalize_age(animal: Dict[str, Any]) -> str:
    """Extract and normalize age string."""
    birthday = animal.get("birthday")
    if birthday:
        age = _compute_age_from_birthday(str(birthday))
        if age:
            return age
    age_group = animal.get("age_group")
    if isinstance(age_group, dict):
        return age_group.get("name", "")
    return ""


def fallback_url(animal_id: str) -> str:
    """Generate Shelterluv profile URL from our animal_id."""
    numeric_id = animal_id.replace(f"{SHELTER_ID}-", "")
    return f"https://new.shelterluv.com/embed/animal/{SHELTERLUV_PREFIX}-A-{numeric_id}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    settings = get_settings()
    store = BarkbotStore(settings, headers=HEADERS)

    targets = store.get_least_recently_updated_urls(
        shelter_id=SHELTER_ID,
        limit=DOGS_PER_RUN,
        fallback_url_fn=fallback_url,
        extra_fields=["age"],
    )

    if not targets:
        print("No adoptable dogs found to scrape.")
        return 0

    print(f"Scraping {len(targets)} SAPA profiles via direct HTTP.")

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run("cron_sapa_profiles", len(targets))
    start_time = time.time()

    try:
        for target in targets:
            # 4-Minute timeout check
            if time.time() - start_time > MAX_EXECUTION_TIME_SECONDS:
                print("Execution time exceeded 4 minutes limit. Stopping early.")
                break

            url = target["url"]
            if not url:
                continue

            # Redirect non-Shelterluv URLs to the Shelterluv embed
            if 'shelterluv.com' not in url:
                url = fallback_url(target["animal_id"])

            processed += 1
            try:
                animal, image_url = fetch_shelterluv_profile(url)

                if animal is None:
                    logging.warning(f"No profile data for {target['animal_id']} at {url}")
                    errors += 1
                    continue

                # Filter out non-dogs (cats, rabbits, etc.)
                species = (animal.get("species") or "").strip().lower()
                if species and species != "dog":
                    logging.info(f"Skipping {target['animal_id']} — species: {species}")
                    raise ValueError("NOT_A_DOG")

                bio = _build_bio(animal)
                weight = _normalize_weight(animal)
                age = _normalize_age(animal)

                record = {
                    "shelter_profile_url": url,
                    "animal_id": target["animal_id"],
                    "shelter_name": SHELTER_NAME,
                    "name": animal.get("name") or target.get("name", ""),
                    "gender": animal.get("sex") or target.get("gender", ""),
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

                try:
                    image_file, image_public_url = store.upload_image(
                        record["animal_id"], record.get("shelter_image_url")
                    )
                    if image_file and image_public_url:
                        record["image_file"] = image_file
                        record["image_public_url"] = image_public_url
                except Exception as img_exc:
                    print(f"Failed to upload image for {record['animal_id']}: {img_exc}", file=sys.stderr)

                result = store.save_record(run_id, record)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
                else:
                    unchanged += 1
                print(json.dumps({"animal_id": record["animal_id"], "result": result}, ensure_ascii=False))

            except ValueError as ve:
                if str(ve) == "NOT_FOUND":
                    # Dog was adopted — remove from active_dogs
                    aid = target.get("animal_id", "")
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_404"}))
                    except Exception as del_exc:
                        print(json.dumps({"animal_id": aid, "error": f"Failed to delete: {str(del_exc)}"}), file=sys.stderr)
                    errors += 1
                elif str(ve) == "NOT_A_DOG":
                    # Non-dog animal — remove from all tables
                    aid = target.get("animal_id", "")
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        store.client.table("animals").delete().eq("animal_id", aid).execute()
                        store.client.table("system_prompts_v2").delete().eq("animal_id", aid).execute()
                        store.client.table("animal_fact_profiles").delete().eq("animal_id", aid).execute()
                        store.client.table("animal_persona_profiles").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_not_a_dog"}))
                    except Exception as del_exc:
                        print(json.dumps({"animal_id": aid, "error": f"Failed to delete NOT_A_DOG: {str(del_exc)}"}), file=sys.stderr)
                else:
                    errors += 1
                    print(json.dumps({"url": url, "error": str(ve)}), file=sys.stderr)
            except Exception as exc:
                errors += 1
                print(json.dumps({"url": url, "error": str(exc)}), file=sys.stderr)

            time.sleep(settings.scrape_sleep_seconds)

        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
        print(f"Done. processed={processed} inserted={inserted} updated={updated} unchanged={unchanged} errors={errors}")
        return 0

    except Exception as exc:
        store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
