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
from bs4 import BeautifulSoup
from supabase import create_client

# Import HSSA specific scraping logic
from lib_hssa_parser import build_record, extension_from_response_or_url

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TRACKED_FIELDS = [
    "url",
    "animal_id",
    "located_at",
    "description",
    "weight",
    "age",
    "more_info",
    "bio",
    "data_updated",
    "image_url",
    "image_file",
    "image_public_url",
]

DOGS_PER_RUN = 30

@dataclass
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str
    scrape_sleep_seconds: float


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_settings() -> Settings:
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
                        
    try:
        return Settings(
            supabase_url=os.environ["storage_SUPABASE_URL"],
            supabase_service_role_key=os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"],
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "animal-images"),
            scrape_sleep_seconds=float(os.getenv("SCRAPE_SLEEP_SECONDS", "1.5")),
        )
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


def download_image_bytes(image_url: str) -> Tuple[bytes, str]:
    response = requests.get(image_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    ext = extension_from_response_or_url(response, image_url)
    return response.content, ext


def fetch_record(url: str, numeric_id: str) -> Dict[str, Any]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    record = build_record(response.text, pet_id=numeric_id)
    record["data_updated"] = now_iso()
    record["image_file"] = None
    record["image_public_url"] = None
    return record


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

    def get_next_version_no(self, animal_id: str) -> int:
        resp = self.client.table("animal_versions").select("version_no").eq("animal_id", animal_id).order("version_no", desc=True).limit(1).execute()
        if not resp.data:
            return 1
        return int(resp.data[0]["version_no"]) + 1

    def save_record(self, run_id: int, record: Dict[str, Any]) -> str:
        current = self.get_current_animal(record["animal_id"])
        changed_fields, diff = compute_diff(current, record)
        change_type = "inserted" if current is None else ("updated" if changed_fields else "unchanged")

        payload = dict(record)
        payload["record_hash"] = record_hash(record)
        payload["last_scrape_run_id"] = run_id
        payload["updated_at"] = now_iso()
        payload.setdefault("qa_status", "pending")
        if current is None:
            payload["created_at"] = now_iso()

        if change_type in {"inserted", "updated"}:
            self.client.table("animals").upsert(payload, on_conflict="animal_id").execute()
            version_no = self.get_next_version_no(record["animal_id"])
            self.client.table("animal_versions").insert({
                "animal_id": record["animal_id"],
                "version_no": version_no,
                "captured_at": now_iso(),
                "snapshot": record,
                "record_hash": payload["record_hash"],
                "scrape_run_id": run_id,
            }).execute()
            self.client.table("animal_change_events").insert({
                "animal_id": record["animal_id"],
                "change_type": change_type,
                "changed_fields": changed_fields,
                "diff": diff,
                "scrape_run_id": run_id,
                "created_at": now_iso(),
            }).execute()
        else:
            self.client.table("animals").update({
                "last_scrape_run_id": run_id,
                "updated_at": now_iso(),
            }).eq("animal_id", record["animal_id"]).execute()

        return change_type
    
    def get_least_recently_updated_hssa_dogs(self, limit: int = DOGS_PER_RUN) -> List[Dict[str, str]]:
        # Get all currently adoptable dogs for HSSA
        adoptable_resp = self.client.table("active_dogs").select("animal_id").eq("shelter_id", "HSSA").execute()
        adoptable_ids = [row["animal_id"] for row in adoptable_resp.data]

        if not adoptable_ids:
            return []

        # Get the update times for dogs already in the animals table
        animals_resp = self.client.table("animals").select("animal_id, updated_at").execute()
        updated_times = {row["animal_id"]: row["updated_at"] for row in animals_resp.data if row["updated_at"]}

        def get_time(aid: str):
            return updated_times.get(aid, "")

        adoptable_ids.sort(key=get_time)
        top_ids = adoptable_ids[:limit]
        
        # HSSA animal_id format: hssa-12345
        dogs = []
        for aid in top_ids:
            numeric_id = aid.replace("hssa-", "")
            dogs.append({
                "animal_id": aid,
                "numeric_id": numeric_id,
                "url": f"https://www.adoptapet.com/pet/{numeric_id}"
            })
        return dogs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    store = BarkbotStore(settings)
    
    dogs = store.get_least_recently_updated_hssa_dogs(limit=DOGS_PER_RUN)
    
    if not dogs:
        print("No adoptable HSSA dogs found to scrape.")
        return 0
    
    print(f"Scraping the following {len(dogs)} HSSA dogs:")
    for d in dogs:
        print(f" - {d['url']}")

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run(args.triggered_by, len(dogs))

    try:
        for d in dogs:
            processed += 1
            url = d["url"]
            aid = d["animal_id"]
            numeric_id = d["numeric_id"]
            try:
                record = fetch_record(url, numeric_id)
                image_file, image_public_url = store.upload_image(record["animal_id"], record.get("image_url"))
                record["image_file"] = image_file
                record["image_public_url"] = image_public_url
                result = store.save_record(run_id, record)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
                else:
                    unchanged += 1
                print(json.dumps({"animal_id": record["animal_id"], "result": result}, ensure_ascii=False))
            except requests.exceptions.HTTPError as exc:
                errors += 1
                if exc.response.status_code in (404, 500, 410):
                    # If the server throws a 404, the animal was likely adopted/removed.
                    # We delete it from active_dogs so we skip it in future update processes.
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_due_to_http_error", "status_code": exc.response.status_code}, ensure_ascii=False))
                    except Exception as del_exc:
                        print(json.dumps({"url": url, "error": f"Failed to delete after HTTP {exc.response.status_code}: {str(del_exc)}"}, ensure_ascii=False), file=sys.stderr)
                else:
                    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            except Exception as exc:
                errors += 1
                print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            time.sleep(settings.scrape_sleep_seconds)

        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
        return 0
    except Exception as exc:
        store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
