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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from supabase import create_client

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
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
        return Settings(
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "animal-images"),
            scrape_sleep_seconds=float(os.getenv("SCRAPE_SLEEP_SECONDS", "1")),
        )
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


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
    animal_id = get_animal_id_from_url(url)

    description_node = soup.select_one("span.text_Description.details")
    weight_node = soup.select_one("span.text_Weight.details")
    age_node = soup.select_one("span.text_Age.details")
    more_info_node = soup.select_one("span.text_MoreInfo.details")
    bio_node = soup.select_one("div.line_Bio.details span.text_Bio.details")
    data_updated_node = soup.select_one("span.text_DataUpdated.details")
    located_at_node = soup.select_one("span.text_LocatedAt.details")

    image_url = extract_image_url(soup)

    return {
        "url": url,
        "animal_id": animal_id,
        "located_at": text_or_none(located_at_node),
        "description": text_or_none(description_node),
        "weight": text_or_none(weight_node),
        "age": text_or_none(age_node),
        "more_info": text_or_none(more_info_node),
        "bio": text_or_none(bio_node),
        "data_updated": text_or_none(data_updated_node),
        "image_url": image_url,
        "image_file": None,
        "image_public_url": None,
    }


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


def fetch_record(url: str) -> Dict[str, Any]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return extract_profile_from_html(response.text, url)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", dest="urls", help="One or more detail URLs to scrape")
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def get_urls(args: argparse.Namespace) -> List[str]:
    if args.urls:
        return args.urls
    raw = os.getenv("SCRAPE_URLS_JSON", "[]")
    urls = json.loads(raw)
    if not isinstance(urls, list) or not urls:
        raise RuntimeError("Provide URLs with --url or SCRAPE_URLS_JSON")
    return [str(u) for u in urls]


def main() -> int:
    args = parse_args()
    settings = get_settings()
    urls = get_urls(args)
    store = BarkbotStore(settings)

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run(args.triggered_by, len(urls))

    try:
        for url in urls:
            processed += 1
            try:
                record = fetch_record(url)
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
            except Exception as exc:
                errors += 1
                print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            time.sleep(settings.scrape_sleep_seconds)

        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
        return 0 if errors == 0 else 1
    except Exception as exc:
        store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
