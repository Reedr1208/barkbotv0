import json
import os
import re
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
from urllib.parse import urlparse, unquote
import hashlib
import mimetypes

import requests
from supabase import create_client

API_URL = "https://mpr-public-api.uk.r.appspot.com/dogs"
SITE_BASE_URL = "https://www.muddypawsrescue.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.muddypawsrescue.org/adoptable-dogs",
}

IMAGE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.muddypawsrescue.org/adoptable-dogs",
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_supabase_client():
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc

def clean_text(value):
    """Normalize whitespace while preserving readable descriptions."""
    if value is None:
        return ""
    value = str(value).replace("\xa0", " ")
    value = re.sub(r"\r\n|\r", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()

def extract_photo_url(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("url", "URL", "Url", "PhotoUrl", "PhotoURL", "Photo", "ImageUrl", "ImageURL", "imageUrl", "src"):
            if value.get(key):
                return str(value[key]).strip()
    return str(value).strip()

def choose_main_image_url(dog):
    cover_photo = extract_photo_url(dog.get("CoverPhoto"))
    if cover_photo:
        return cover_photo
    photos = dog.get("Photos") or []
    if isinstance(photos, list):
        for photo in photos:
            photo_url = extract_photo_url(photo)
            if photo_url:
                return photo_url
    else:
        photo_url = extract_photo_url(photos)
        if photo_url:
            return photo_url
    return ""

def guess_extension(content_type: str, image_url: str) -> str:
    if content_type:
        ct = content_type.lower()
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"

    path = urlparse(image_url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if path.endswith(ext):
            return ext
    return ".jpg"

def fetch_dogs():
    response = requests.get(API_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    dogs = response.json()
    if not isinstance(dogs, list):
        raise ValueError(f"Expected a list of dogs, got: {type(dogs)}")
    return dogs

def record_hash(record: dict) -> str:
    tracked_fields = [
        "shelter_profile_url", "animal_id", "shelter_name", "weight", "age",
        "more_info", "bio", "shelter_image_url", "image_file", "image_public_url", "raw_data_jsonb",
        "city", "state", "shelter_id"
    ]
    canonical = {k: record.get(k) for k in tracked_fields}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def upload_image(client, bucket: str, animal_id: str, image_url: str):
    if not image_url:
        return None, None
    try:
        response = requests.get(image_url, headers=IMAGE_HEADERS, timeout=30)
        response.raise_for_status()
        ext = guess_extension(response.headers.get("Content-Type", ""), image_url)
        object_path = f"animals/{animal_id}{ext}"
        
        client.storage.from_(bucket).upload(
            object_path,
            response.content,
            file_options={"upsert": "true", "content-type": response.headers.get("Content-Type", "image/jpeg")},
        )
        public_url = client.storage.from_(bucket).get_public_url(object_path)
        return object_path, public_url
    except Exception as e:
        logging.error(f"Failed to upload image for {animal_id}: {e}")
        return None, None

def save_to_supabase(dogs: list):
    if not dogs:
        logging.info("No dogs to save.")
        return

    client = get_supabase_client()
    bucket = os.getenv("SUPABASE_BUCKET", "animal-images")

    active_dogs = []
    animals_upsert = []

    for dog in dogs:
        native_id = dog.get("Animal_ID", "")
        if not native_id:
            continue
            
        name = dog.get("Name", "Unknown").replace("*", "").strip().title()
        gender = dog.get("Sex", "Unknown")
        age = str(dog.get("Age", ""))
        weight = str(dog.get("CurrentWeightPounds", ""))
        
        animal_id = f"MP-{native_id}"
        
        # Build active roster record
        active_dogs.append({
            "shelter_id": "MP",
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "age": age,
            "weight": weight,
            "city": "NYC",
            "state": "NY",
            "shelter_name": "Muddy Paws Rescue",
            "scraped_at": now_iso()
        })
        
        # Build detailed animals record
        image_url = choose_main_image_url(dog)
        image_file, image_public_url = upload_image(client, bucket, animal_id, image_url)
        
        bio = clean_text(dog.get("Description", ""))
        
        animals_record = {
            "shelter_profile_url": f"{SITE_BASE_URL}/adoptable?dog={native_id}",
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "shelter_name": "Muddy Paws Rescue",
            "city": "NYC",
            "state": "NY",
            "shelter_id": "MP",
            "weight": weight,
            "age": age,
            "more_info": None,
            "bio": bio,
            "shelter_image_url": image_url,
            "image_file": image_file,
            "image_public_url": image_public_url,
            "raw_data_jsonb": dog,
            "updated_at": now_iso()
        }
        animals_record["record_hash"] = record_hash(animals_record)
        
        # We need to maintain created_at
        existing = client.table("animals").select("created_at").eq("animal_id", animal_id).limit(1).execute()
        if existing.data:
            animals_record["created_at"] = existing.data[0].get("created_at")
        else:
            animals_record["created_at"] = now_iso()
            
        animals_upsert.append(animals_record)

    # 1. Wipe and replace active_dogs for MP
    logging.info("Clearing existing active_dogs table data for MP...")
    client.table("active_dogs").delete().eq("shelter_id", "MP").execute()

    logging.info(f"Inserting {len(active_dogs)} dogs into active_dogs...")
    client.table("active_dogs").insert(active_dogs).execute()

    # 2. Upsert detailed animals
    logging.info(f"Upserting {len(animals_upsert)} dogs into animals...")
    # Supabase bulk upsert
    for chunk_start in range(0, len(animals_upsert), 50):
        chunk = animals_upsert[chunk_start:chunk_start + 50]
        client.table("animals").upsert(chunk, on_conflict="animal_id").execute()

if __name__ == "__main__":
    logging.info("Starting scrape...")
    dogs = fetch_dogs()
    logging.info(f"Fetched {len(dogs)} dogs from MuddyPaws.")
    save_to_supabase(dogs)
    logging.info("Scrape completed successfully.")
