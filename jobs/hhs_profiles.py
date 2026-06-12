import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from supabase import create_client
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

TRACKED_FIELDS = [
    "shelter_profile_url",
    "animal_id",
    "name",
    "gender",
    "shelter_name",
    "weight",
    "age",
    "more_info",
    "bio",
    "shelter_image_url",
    "image_file",
    "image_public_url",
    "city",
    "state",
    "shelter_id"
]

DOGS_PER_RUN = 30
MAX_EXECUTION_TIME_SECONDS = 240  # 4 minutes

@dataclass
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str
    scrape_sleep_seconds: float


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_settings() -> Settings:
    try:
        url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise KeyError("Missing Supabase credentials")
        return Settings(
            supabase_url=url,
            supabase_service_role_key=key,
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "animal-images"),
            scrape_sleep_seconds=float(os.getenv("SCRAPE_SLEEP_SECONDS", "1")),
        )
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


def guess_extension(content_type: Optional[str], image_url: str) -> str:
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


def download_image_bytes(image_url: str) -> Tuple[bytes, str]:
    response = requests.get(image_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    ext = guess_extension(response.headers.get("Content-Type"), image_url)
    return response.content, ext


def record_hash(record: Dict[str, Any]) -> str:
    canonical = {k: record.get(k) for k in TRACKED_FIELDS}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_diff(old: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    if not old:
        changed_fields = list(TRACKED_FIELDS)
        diff = {field: {"old": None, "new": new.get(field)} for field in changed_fields}
        return changed_fields, diff

    changed_fields: List[str] = []
    diff: Dict[str, Dict[str, Any]] = {}
    for field in TRACKED_FIELDS:
        old_val = old.get(field)
        new_val = new.get(field)
        if old_val != new_val:
            changed_fields.append(field)
            diff[field] = {"old": old_val, "new": new_val}
    return changed_fields, diff


class BarkbotStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def begin_run(self, triggered_by: str, source_count: int) -> int:
        payload = {
            "triggered_by": triggered_by,
            "source_count": source_count,
            "started_at": now_iso(),
            "status": "running",
        }
        row = self.client.table("scrape_runs").insert(payload).execute().data[0]
        return row["id"]

    def finish_run(self, run_id: int, status: str, processed: int, inserted: int, updated: int, unchanged: int, errors: int, notes: Optional[str] = None) -> None:
        payload = {
            "status": status,
            "processed_count": processed,
            "inserted_count": inserted,
            "updated_count": updated,
            "unchanged_count": unchanged,
            "error_count": errors,
            "notes": notes,
            "finished_at": now_iso(),
        }
        self.client.table("scrape_runs").update(payload).eq("id", run_id).execute()

    def get_current_animal(self, animal_id: str) -> Optional[Dict[str, Any]]:
        resp = self.client.table("animals").select("*").eq("animal_id", animal_id).limit(1).execute()
        return resp.data[0] if resp.data else None

    def upload_image(self, animal_id: str, image_url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not image_url:
            return None, None
        content, ext = download_image_bytes(image_url)
        object_path = f"animals/{animal_id}{ext}"
        self.client.storage.from_(self.settings.supabase_bucket).upload(
            object_path,
            content,
            file_options={"upsert": "true", "content-type": requests.head(image_url, headers=HEADERS, timeout=30).headers.get("Content-Type", "image/jpeg")},
        )
        public_url = self.client.storage.from_(self.settings.supabase_bucket).get_public_url(object_path)
        return object_path, public_url

    def save_record(self, run_id: int, record: Dict[str, Any]) -> str:
        current = self.get_current_animal(record["animal_id"])
        changed_fields, diff = compute_diff(current, record)
        change_type = "inserted" if current is None else ("updated" if changed_fields else "unchanged")

        payload = dict(record)
        payload["record_hash"] = record_hash(record)
        payload["last_scrape_run_id"] = run_id
        payload["updated_at"] = now_iso()
        if current is None:
            payload["created_at"] = now_iso()

        self.client.table("animals").upsert(payload, on_conflict="animal_id").execute()
        return change_type
    
    def get_least_recently_updated_urls(self, limit: int = DOGS_PER_RUN) -> List[Dict[str, Any]]:
        adoptable_resp = self.client.table("active_dogs").select("animal_id, name, gender, age, shelter_profile_url, public_image_url").eq("shelter_id", "HHS").execute()
        adoptable_dogs = {row["animal_id"]: row for row in adoptable_resp.data}
        adoptable_ids = list(adoptable_dogs.keys())

        if not adoptable_ids:
            return []

        animals_resp = self.client.table("animals").select("animal_id, updated_at").execute()
        updated_times = {row["animal_id"]: row["updated_at"] for row in animals_resp.data if row["updated_at"]}

        def get_time(aid: str):
            return updated_times.get(aid, "")

        adoptable_ids.sort(key=get_time)
        
        top_ids = adoptable_ids[:limit]
        
        results = []
        for aid in top_ids:
            dog = adoptable_dogs[aid]
            results.append({
                "url": dog.get("shelter_profile_url"),
                "animal_id": aid,
                "name": dog.get("name"),
                "gender": dog.get("gender"),
                "age": dog.get("age"),
                "public_image_url": dog.get("public_image_url"),
            })
        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def extract_bio_with_playwright(page, url: str) -> str:
    logging.info(f"Navigating to {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass

        # Try to find common text containers, otherwise fallback to body
        bio_text = page.evaluate('''() => {
            let el = document.querySelector('.animal-details, .profile-info, .description');
            if (el) return el.innerText;
            return document.body.innerText;
        }''')
        return bio_text.strip() if bio_text else ""
    except Exception as e:
        logging.error(f"Playwright failed to fetch {url}: {e}")
        return ""


def main() -> int:
    args = parse_args()
    settings = get_settings()
    store = BarkbotStore(settings)
    
    targets = store.get_least_recently_updated_urls(limit=DOGS_PER_RUN)
    
    if not targets:
        print("No adoptable dogs found to scrape.")
        return 0
    
    print(f"Scraping the following {len(targets)} URLs:")
    for t in targets:
        print(f" - {t['url']}")

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run(args.triggered_by, len(targets))
    start_time = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            for target in targets:
                # 4-Minute timeout check
                if time.time() - start_time > MAX_EXECUTION_TIME_SECONDS:
                    print("Execution time exceeded 4 minutes limit. Stopping early.")
                    break

                url = target["url"]
                if not url:
                    continue

                processed += 1
                try:
                    bio = extract_bio_with_playwright(page, url)
                    record = {
                        "shelter_profile_url": url,
                        "animal_id": target["animal_id"],
                        "shelter_name": "Houston Humane Society",
                        "name": target["name"],
                        "gender": target["gender"],
                        "age": target["age"],
                        "weight": None, # Weight is difficult to parse reliably here, pipeline can extract from bio
                        "more_info": "",
                        "bio": bio,
                        "shelter_image_url": target["public_image_url"],
                        "image_file": None,
                        "image_public_url": None,
                        "city": "Houston",
                        "state": "TX",
                        "shelter_id": "HHS"
                    }
                    
                    try:
                        image_file, image_public_url = store.upload_image(record["animal_id"], record.get("shelter_image_url"))
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
                except Exception as exc:
                    errors += 1
                    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
                
                time.sleep(settings.scrape_sleep_seconds)

            final_status = "success" if errors == 0 else "partial_success"
            store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
            
            browser.close()
            return 0
        except Exception as exc:
            store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
            browser.close()
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(main())
