import json
import os
import re
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urljoin
import hashlib
import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client
from jobs.lib.image import upload_image as _upload_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- WWLA Config ---
LISTING_URL = "https://www.wagsandwalks.org/available-dogs-la"
BASE_URL = "https://www.wagsandwalks.org"
REQUEST_TIMEOUT_SECONDS = 45
EXCLUDE_SOLD_OUT = True

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def clean_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

def normalize_image_url(url: str) -> str:
    url = clean_text(url)
    if not url:
        return ""
    url = url.split()[0]
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.netloc.endswith("squarespace-cdn.com") and parsed.query:
        return urlunparse(parsed._replace(query=""))
    return url

def record_hash(record: dict) -> str:
    """WWLA-specific record hash — includes raw_data_jsonb."""
    tracked_fields = [
        "shelter_profile_url", "animal_id", "shelter_name", "weight", "age",
        "more_info", "bio", "shelter_image_url", "image_file", "image_public_url", "raw_data_jsonb",
        "city", "state", "shelter_id"
    ]
    canonical = {k: record.get(k) for k in tracked_fields}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def upload_image(client, bucket: str, animal_id: str, image_url: str):
    return _upload_image(client, bucket, animal_id, image_url, headers=IMAGE_HEADERS)

# --- Scraping Logic ---
def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": IMAGE_HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    logging.info("Fetching %s", url)
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text

def description_html_to_lines(description_html: str) -> list:
    if not description_html:
        return []
    soup = BeautifulSoup(description_html, "html.parser")
    text_with_breaks = soup.get_text("\n", strip=True)
    return [clean_text(line) for line in text_with_breaks.splitlines() if clean_text(line)]

def extract_labeled_value(description_html: str, label: str) -> str:
    lines = description_html_to_lines(description_html)
    label_pattern = re.compile(r"^" + re.escape(label) + r"\s*:\s*(.+)$", flags=re.IGNORECASE)
    for line in lines:
        match = label_pattern.match(line)
        if match:
            return clean_text(match.group(1))
    
    compact_text = clean_text(" ".join(lines))
    stop_labels = "Breed|Age|Gender|Weight|Size|Apply to Adopt"
    pattern = re.compile(
        r"\b" + re.escape(label) + r"\s*:\s*(.*?)(?=\s+(?:" + stop_labels + r")\s*:|\s+Apply to Adopt\b|$)",
        flags=re.IGNORECASE,
    )
    match = pattern.search(compact_text)
    if match:
        return clean_text(match.group(1))
    return ""

def clean_weight_value(value: str) -> str:
    value = clean_text(value)
    if not value: return ""
    value = re.split(r"\bApply to Adopt\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    weight_pattern = re.compile(
        r"\b((?:approx(?:imately)?\.?\s*)?(?:(?:about|around|under|over|up to|less than|more than)\s+)?"
        r"\d+(?:\.\d+)?(?:\s*(?:&|and|/|-|–|to)\s*\d+(?:\.\d+)?)*\s*(?:lbs?|pounds?))\b",
        flags=re.IGNORECASE,
    )
    match = weight_pattern.search(value)
    if match: return clean_text(match.group(1))
    if len(value) <= 35: return value.rstrip(" .;,")
    return ""

def sanitize_weight_for_csv(weight: str) -> str:
    weight = clean_text(weight).replace("\u2060", " ").replace("\xa0", " ")
    unit_match = re.search(r"\b(?:lbs?|pounds?)\b", weight, flags=re.IGNORECASE)
    if unit_match: weight = weight[: unit_match.end()]
    weight = clean_text(weight).strip(" .;,|:-")
    if len(weight) > 10: weight = weight[:10].strip(" .;,|:-")
    return weight

def parse_records(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    payloads = []
    for tag in soup.find_all(attrs={"data-context": True}):
        raw = tag.get("data-context") or ""
        if "items" not in raw: continue
        try:
            payload = json.loads(raw)
            if payload.get("items"): payloads.append(payload)
        except json.JSONDecodeError:
            pass

    records = []
    seen = set()
    for payload in payloads:
        for item in payload.get("items", []):
            if not isinstance(item, dict): continue
            if EXCLUDE_SOLD_OUT and item.get("soldOut") is True: continue
            
            native_id = clean_text(item.get("id")) or clean_text(item.get("urlSlug"))
            if not native_id: continue
            
            key = native_id
            if key in seen: continue
            seen.add(key)
            
            name = clean_text(item.get("title"))
            full_url = clean_text(item.get("fullUrl"))
            shelter_profile_url = urljoin(BASE_URL, full_url) if full_url else ""
            
            main_image = item.get("mainImage", {})
            public_image_url = normalize_image_url(main_image.get("assetUrl", ""))
            if not public_image_url and item.get("images"):
                public_image_url = normalize_image_url(item["images"][0].get("assetUrl", ""))
            
            description_html = item.get("description", "")
            bio = clean_text(" ".join(description_html_to_lines(description_html)))
            weight_raw = extract_labeled_value(description_html, "Weight")
            weight = sanitize_weight_for_csv(clean_weight_value(weight_raw))
            gender = extract_labeled_value(description_html, "Gender")
            age = extract_labeled_value(description_html, "Age")
            
            records.append({
                "native_id": native_id,
                "name": name,
                "shelter_profile_url": shelter_profile_url,
                "public_image_url": public_image_url,
                "gender": gender,
                "age": age,
                "weight": weight,
                "bio": bio,
                "raw_data_jsonb": item
            })
    return records

def save_to_supabase(dogs: list):
    if not dogs:
        logging.info("No dogs to save.")
        return

    client = get_supabase_client()
    bucket = os.getenv("SUPABASE_BUCKET", "animal-images")

    active_dogs = []
    animals_upsert = []

    for dog in dogs:
        native_id = dog["native_id"]
        animal_id = f"WWLA-{native_id}"
        
        name = dog.get("name", "Unknown").replace("*", "").strip().title()
        gender = dog.get("gender", "Unknown")
        age = dog.get("age", "")
        weight = dog.get("weight", "")
        
        active_dogs.append({
            "shelter_id": "WWLA",
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "age": age,
            "weight": weight,
            "city": "Los Angeles",
            "state": "CA",
            "shelter_name": "Wags & Walks LA",
            "shelter_profile_url": dog["shelter_profile_url"],
            "scraped_at": now_iso()
        })
        
        image_url = dog["public_image_url"]
        image_file, image_public_url = upload_image(client, bucket, animal_id, image_url)
        
        bio = clean_text(dog.get("bio", ""))
        
        animals_record = {
            "shelter_profile_url": dog["shelter_profile_url"],
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "shelter_name": "Wags & Walks LA",
            "city": "Los Angeles",
            "state": "CA",
            "shelter_id": "WWLA",
            "weight": weight,
            "age": age,
            "more_info": None,
            "bio": bio,
            "shelter_image_url": image_url,
            "image_file": image_file,
            "image_public_url": image_public_url,
            "raw_data_jsonb": dog["raw_data_jsonb"],
            "updated_at": now_iso()
        }
        animals_record["record_hash"] = record_hash(animals_record)
        
        existing = client.table("animals").select("created_at").eq("animal_id", animal_id).limit(1).execute()
        if existing.data:
            animals_record["created_at"] = existing.data[0].get("created_at")
        else:
            animals_record["created_at"] = now_iso()
            
        animals_upsert.append(animals_record)

    logging.info("Clearing existing active_dogs table data for WWLA...")
    client.table("active_dogs").delete().eq("shelter_id", "WWLA").execute()

    logging.info(f"Inserting {len(active_dogs)} dogs into active_dogs...")
    client.table("active_dogs").insert(active_dogs).execute()

    logging.info(f"Upserting {len(animals_upsert)} dogs into animals...")
    for chunk_start in range(0, len(animals_upsert), 50):
        chunk = animals_upsert[chunk_start:chunk_start + 50]
        client.table("animals").upsert(chunk, on_conflict="animal_id").execute()

if __name__ == "__main__":
    logging.info("Starting WWLA scrape...")
    html = fetch_html(LISTING_URL)
    dogs = parse_records(html)
    logging.info(f"Fetched {len(dogs)} dogs from WWLA.")
    save_to_supabase(dogs)
    logging.info("WWLA Scrape completed successfully.")
