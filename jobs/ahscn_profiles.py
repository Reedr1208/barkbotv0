#!/usr/bin/env python3
"""
Scrape AHS Newark dog profile pages and upsert into Supabase `animals` table.
"""

import os
import json
import re
import sys
import time
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from supabase import create_client

# =============================================================================
# Inputs / configuration
# =============================================================================

SHELTER_ID = "AHSCN"
CITY = "Newark"
STATE = "NJ"
SHELTER_NAME = "Associated Humane Societies - Newark"

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_SLEEP_SECONDS = 0.5
MAX_EXECUTION_TIME_SECONDS = 240  # 4 minutes max before stopping
DOGS_PER_RUN = 50

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

TRACKED_FIELDS = {
    "shelter_profile_url",
    "animal_id",
    "name",
    "shelter_name",
    "weight",
    "age",
    "more_info",
    "bio",
    "shelter_image_url",
    "image_public_url",
    "city",
    "state",
    "shelter_id",
    "gender",
}

# =============================================================================
# Utility helpers
# =============================================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def clean_text(value: Any) -> str:
    if value is None:
        return ""
    import html
    text = str(value)
    text = html.unescape(text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text("\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def compact_join(parts: Iterable[str], sep: str = "\n\n") -> str:
    cleaned = [p.strip() for p in parts if p and p.strip()]
    return sep.join(cleaned)

def label_from_camel_or_snake(value: str) -> str:
    special = {
        "goodWithDogs": "Good with Dogs",
        "goodWithCats": "Good with Cats",
        "goodWithChildren": "Good with Children",
        "spayedNeutered": "Spayed/neutered",
        "housetrained": "House-trained",
    }
    if value in special:
        return special[value]
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"(?<!^)(?=[A-Z])", " ", value)
    return value.title().replace("With", "with")

def get_attr(attributes: List[Dict[str, Any]], label: str) -> str:
    wanted = label.lower().strip()
    for item in attributes or []:
        if str(item.get("label", "")).lower().strip() == wanted:
            return clean_text(item.get("content"))
    return ""

def guess_extension(content_type: Optional[str], image_url: str) -> str:
    if content_type:
        ct = content_type.lower()
        if "jpeg" in ct or "jpg" in ct: return ".jpg"
        if "png" in ct: return ".png"
        if "webp" in ct: return ".webp"
        if "gif" in ct: return ".gif"
    path = urlparse(image_url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if path.endswith(ext): return ext
    return ".jpg"

def download_image_bytes(image_url: str) -> Tuple[bytes, str]:
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(image_url, headers=headers, timeout=30)
    response.raise_for_status()
    ext = guess_extension(response.headers.get("Content-Type"), image_url)
    return response.content, ext

# =============================================================================
# Barkbot Store Logic
# =============================================================================

def record_hash(record: Dict[str, Any]) -> str:
    canonical = {k: record.get(k) for k in TRACKED_FIELDS}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def compute_diff(old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    if not old:
        changed = list(TRACKED_FIELDS)
        diff = {f: {"old": None, "new": new.get(f)} for f in changed}
        return changed, diff
    changed = []
    diff = {}
    for f in TRACKED_FIELDS:
        if old.get(f) != new.get(f):
            changed.append(f)
            diff[f] = {"old": old.get(f), "new": new.get(f)}
    return changed, diff

class BarkbotStore:
    def __init__(self, client):
        self.client = client
        self.bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")

    def begin_run(self, triggered_by: str, source_count: int) -> int:
        payload = {"triggered_by": triggered_by, "source_count": source_count, "started_at": now_iso(), "status": "running"}
        row = self.client.table("scrape_runs").insert(payload).execute().data[0]
        return row["id"]

    def finish_run(self, run_id: int, status: str, processed: int, inserted: int, updated: int, unchanged: int, errors: int, notes: Optional[str] = None) -> None:
        payload = {"status": status, "processed_count": processed, "inserted_count": inserted, "updated_count": updated, "unchanged_count": unchanged, "error_count": errors, "notes": notes, "finished_at": now_iso()}
        self.client.table("scrape_runs").update(payload).eq("id", run_id).execute()

    def get_current_animal(self, animal_id: str) -> Optional[Dict[str, Any]]:
        resp = self.client.table("animals").select("*").eq("animal_id", animal_id).limit(1).execute()
        return resp.data[0] if resp.data else None

    def upload_image(self, animal_id: str, image_url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not image_url: return None, None
        try:
            content, ext = download_image_bytes(image_url)
            object_path = f"animals/{animal_id}{ext}"
            content_type = requests.head(image_url, headers={"User-Agent": USER_AGENT}, timeout=30).headers.get("Content-Type", "image/jpeg")
            self.client.storage.from_(self.bucket).upload(object_path, content, file_options={"upsert": "true", "content-type": content_type})
            public_url = self.client.storage.from_(self.bucket).get_public_url(object_path)
            return object_path, public_url
        except Exception as e:
            logging.error(f"Failed to upload image for {animal_id}: {e}")
            return None, None

    def get_next_version_no(self, animal_id: str) -> int:
        resp = self.client.table("animal_versions").select("version_no").eq("animal_id", animal_id).order("version_no", desc=True).limit(1).execute()
        return int(resp.data[0]["version_no"]) + 1 if resp.data else 1

    def save_record(self, run_id: int, record: Dict[str, Any]) -> str:
        current = self.get_current_animal(record["animal_id"])
        changed, diff = compute_diff(current, record)
        change_type = "inserted" if current is None else ("updated" if changed else "unchanged")

        payload = dict(record)
        payload["record_hash"] = record_hash(record)
        payload["updated_at"] = now_iso()
        if not current: payload["created_at"] = now_iso()

        if change_type in ("inserted", "updated"):
            if change_type == "inserted":
                self.client.table("animals").insert(payload).execute()
            else:
                self.client.table("animals").update(payload).eq("animal_id", record["animal_id"]).execute()

            version_payload = {
                "animal_id": record["animal_id"],
                "version_no": self.get_next_version_no(record["animal_id"]),
                "record_hash": payload["record_hash"],
                "scraped_at": payload["updated_at"],
                "run_id": run_id,
                "raw_data": record,
            }
            version_id = self.client.table("animal_versions").insert(version_payload).execute().data[0]["id"]
            if change_type == "updated":
                for field_name, vals in diff.items():
                    event_payload = {"animal_id": record["animal_id"], "version_id": version_id, "field_name": field_name, "old_value": vals["old"], "new_value": vals["new"], "changed_at": payload["updated_at"]}
                    self.client.table("animal_change_events").insert(event_payload).execute()
        return change_type

    def get_least_recently_updated_urls(self, limit: int = DOGS_PER_RUN) -> List[Dict[str, str]]:
        adoptable_resp = self.client.table("active_dogs").select("animal_id, name, gender, shelter_profile_url, public_image_url").eq("shelter_id", SHELTER_ID).execute()
        if not adoptable_resp.data: return []
        adoptable = adoptable_resp.data
        adoptable_ids = [d["animal_id"] for d in adoptable]

        updated_times = {}
        for i in range(0, len(adoptable_ids), 100):
            chunk = adoptable_ids[i:i+100]
            animals_resp = self.client.table("animals").select("animal_id, updated_at").in_("animal_id", chunk).execute()
            for r in animals_resp.data: updated_times[r["animal_id"]] = r["updated_at"]

        adoptable.sort(key=lambda d: updated_times.get(d["animal_id"], ""))
        return adoptable[:limit]


# =============================================================================
# Fetching and extraction
# =============================================================================

def fetch_html(url: str, session: requests.Session) -> Tuple[str, str, int]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    response.raise_for_status()
    return response.text, response.url, response.status_code

def find_matching_braced_object(text: str, start_index: int) -> Optional[str]:
    if start_index < 0 or start_index >= len(text) or text[start_index] != "{": return None
    depth = 0; in_string = False; escaped = False
    for i in range(start_index, len(text)):
        ch = text[i]
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
        else:
            if ch == '"': in_string = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return text[start_index : i + 1]
    return None

def extract_pet_details_from_next_data(html_text: str) -> Optional[Dict[str, Any]]:
    payloads = []
    pattern = re.compile(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)</script>", re.DOTALL)
    for match in pattern.finditer(html_text):
        raw = match.group(1)
        try:
            payloads.append(json.loads('"' + raw + '"'))
        except json.JSONDecodeError:
            pass
            
    for payload in payloads:
        if "PetDetails" not in payload or '"pet"' not in payload: continue
        pet_key_index = payload.find('"pet"')
        object_start = payload.find("{", pet_key_index)
        object_text = find_matching_braced_object(payload, object_start)
        if not object_text: continue
        try:
            pet = json.loads(object_text)
            if isinstance(pet, dict) and pet.get("__typename") == "PetDetails": return pet
        except json.JSONDecodeError:
            continue
    return None

def extract_canonical_url(html_text: str, final_url: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"): return canonical["href"].strip()
    return final_url

# =============================================================================
# Record shaping
# =============================================================================

def trait_lines(pet: Dict[str, Any]) -> List[str]:
    lines = []
    for trait in pet.get("petTraits") or []:
        if isinstance(trait, dict) and trait.get("type") and trait.get("status") is not None:
            label = label_from_camel_or_snake(str(trait.get("type")))
            if trait.get("status") is True: lines.append(label)
            elif trait.get("status") is False: lines.append(f"Not {label}")
            else: lines.append(f"{label}: {trait.get('status')}")
    return lines

def make_bio(pet: Dict[str, Any]) -> str:
    attrs = pet.get("petAttributes") or []
    attr_lines = [f"{clean_text(i.get('label'))}: {clean_text(i.get('content'))}" for i in attrs if i.get("label") and i.get("content")]
    trait_text = "\n".join(f"- {line}" for line in trait_lines(pet))
    parts = [
        f"Name: {clean_text(pet.get('petName'))}" if pet.get("petName") else "",
        "Basic info:\n" + "\n".join(attr_lines) if attr_lines else "",
        "Traits:\n" + trait_text if trait_text else "",
        "My story:\n" + clean_text(pet.get("petStory")) if pet.get("petStory") else "",
    ]
    return compact_join(parts)

def make_more_info(pet: Dict[str, Any]) -> str:
    parts = [
        f"Shelter: {clean_text(pet.get('awoName'))}" if pet.get("awoName") else "",
        "Adoption process:\n" + clean_text(pet.get("awoAdoptionProcess")) if pet.get("awoAdoptionProcess") else "",
    ]
    return compact_join(parts)

def choose_high_res_image_url(pet: Dict[str, Any], html_text: str) -> str:
    candidates = [
        pet.get("petThumbnailUrl"),
        (pet.get("petSocialShareData") or {}).get("thumbnailUrl") if isinstance(pet.get("petSocialShareData"), dict) else "",
        (pet.get("petSocialShareData") or {}).get("sharedPhotoUrl") if isinstance(pet.get("petSocialShareData"), dict) else "",
    ]
    for candidate in candidates:
        candidate = clean_text(candidate)
        if candidate and "Fallback-Photo" not in candidate: return candidate
    return clean_text(candidates[0]) if candidates else ""

# =============================================================================
# Main
# =============================================================================

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_time = time.time()
    
    # Load env for local testing
    from pathlib import Path
    env_local = Path(__file__).resolve().parent.parent / ".env.local"
    env_dev = Path(__file__).resolve().parent.parent / ".env.development.local"
    for env_file in (env_local, env_dev):
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ[k] = v.strip().strip('"').strip("'")
                        
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    client = create_client(supabase_url, supabase_key)
    store = BarkbotStore(client)
    
    dogs_to_process = store.get_least_recently_updated_urls(limit=DOGS_PER_RUN)
    if not dogs_to_process:
        logging.info("No AHSCN dogs found to process.")
        return

    run_id = store.begin_run("ahscn_profiles", len(dogs_to_process)) if not dry_run else 0
    session = requests.Session()
    stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}

    for idx, dog in enumerate(dogs_to_process):
        if time.time() - start_time > MAX_EXECUTION_TIME_SECONDS:
            logging.info("Reached 4-minute limit. Stopping gracefully.")
            break
            
        url = dog["shelter_profile_url"]
        animal_id = dog["animal_id"]
        logging.info(f"[{idx+1}/{len(dogs_to_process)}] Processing {animal_id}: {url}")
        
        try:
            html_text, final_url, _ = fetch_html(url, session)
            pet = extract_pet_details_from_next_data(html_text)
            
            if not pet:
                logging.warning(f"Could not extract PetDetails for {animal_id}.")
                stats["errors"] += 1
                continue
                
            attrs = pet.get("petAttributes") or []
            scraped_image = choose_high_res_image_url(pet, html_text)
            fallback_image = dog.get("public_image_url")
            image_url_to_download = scraped_image if scraped_image else fallback_image
            
            if not dry_run:
                object_path, public_url = store.upload_image(animal_id, image_url_to_download)
            else:
                object_path, public_url = f"animals/{animal_id}.jpg", f"http://fake.url/animals/{animal_id}.jpg"
                
            record = {
                "animal_id": animal_id,
                "name": clean_text(pet.get("petName")) or dog.get("name"),
                "shelter_profile_url": extract_canonical_url(html_text, final_url),
                "weight": get_attr(attrs, "Weight"),
                "age": get_attr(attrs, "Age"),
                "city": CITY,
                "state": STATE,
                "shelter_id": SHELTER_ID,
                "shelter_name": SHELTER_NAME,
                "gender": get_attr(attrs, "Sex") or dog.get("gender"),
                "bio": make_bio(pet),
                "more_info": make_more_info(pet),
                "shelter_image_url": image_url_to_download,
                "image_public_url": public_url,
            }
            
            if not dry_run:
                change_type = store.save_record(run_id, record)
                stats[change_type] += 1
                logging.info(f"Record {animal_id} {change_type}.")
            else:
                stats["inserted"] += 1
                logging.info(f"[DRY RUN] Would save record {animal_id}.")
                
        except Exception as e:
            logging.error(f"Error processing {animal_id}: {e}")
            stats["errors"] += 1
            
        time.sleep(REQUEST_SLEEP_SECONDS)
        
    if not dry_run:
        store.finish_run(run_id, "completed", stats["processed"], stats["inserted"], stats["updated"], stats["unchanged"], stats["errors"])
    
    logging.info(f"Run finished: {stats}")

if __name__ == "__main__":
    main()
