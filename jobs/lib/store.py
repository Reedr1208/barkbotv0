"""
BarkbotStore — the shared data-access layer for profile scrapers.

Consolidates the Settings dataclass, get_settings(), and the full
BarkbotStore class (begin_run, finish_run, get_current_animal,
upload_image, save_record, get_least_recently_updated_urls) that
were copy-pasted across every *_profiles.py.
"""

import os
import sys
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from supabase import create_client

from .db import now_iso, load_env
from .image import download_image_bytes, DEFAULT_HEADERS
from .record import TRACKED_FIELDS, record_hash, compute_diff


DEFAULT_DOGS_PER_RUN = 30


@dataclass
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str
    scrape_sleep_seconds: float


def get_settings(default_sleep: float = 1.0) -> Settings:
    """Read Supabase settings from environment variables."""
    load_env()
    try:
        url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise KeyError("Missing Supabase credentials")
        return Settings(
            supabase_url=url,
            supabase_service_role_key=key,
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "animal-images"),
            scrape_sleep_seconds=float(os.getenv("SCRAPE_SLEEP_SECONDS", str(default_sleep))),
        )
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


class BarkbotStore:
    """
    Shared data-access layer for profile scrapers.

    Handles scrape-run tracking, animal record CRUD, image upload,
    and least-recently-updated scheduling.
    """

    def __init__(self, settings: Settings, headers: dict | None = None):
        self.settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self.headers = headers or DEFAULT_HEADERS

    def begin_run(self, triggered_by: str, source_count: int) -> int:
        payload = {
            "triggered_by": triggered_by,
            "source_count": source_count,
            "started_at": now_iso(),
            "status": "running",
        }
        row = self.client.table("scrape_runs").insert(payload).execute().data[0]
        return row["id"]

    def finish_run(
        self,
        run_id: int,
        status: str,
        processed: int,
        inserted: int,
        updated: int,
        unchanged: int,
        errors: int,
        notes: Optional[str] = None,
    ) -> None:
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
        """Download and upload an image to Supabase Storage. Returns (object_path, public_url)."""
        if not image_url:
            return None, None
        content, ext = download_image_bytes(image_url, headers=self.headers)
        object_path = f"animals/{animal_id}{ext}"
        self.client.storage.from_(self.settings.supabase_bucket).upload(
            object_path,
            content,
            file_options={
                "upsert": "true",
                "content-type": requests.head(
                    image_url, headers=self.headers, timeout=30
                ).headers.get("Content-Type", "image/jpeg"),
            },
        )
        public_url = self.client.storage.from_(self.settings.supabase_bucket).get_public_url(object_path)
        return object_path, public_url

    def save_record(self, run_id: int, record: Dict[str, Any]) -> str:
        """Upsert an animal record, returning 'inserted', 'updated', or 'unchanged'."""
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

    def get_least_recently_updated_urls(
        self,
        shelter_id: str,
        limit: int = DEFAULT_DOGS_PER_RUN,
        fallback_url_fn=None,
        extra_fields: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Get the N least-recently-updated adoptable dogs for a shelter.

        Args:
            shelter_id: The shelter ID to filter by (e.g. "PACC", "HSSA")
            limit: Max number of dogs to return
            fallback_url_fn: Optional function(animal_id) -> str for building
                             fallback URLs when shelter_profile_url is missing
            extra_fields: Additional fields to select from active_dogs
        """
        select_fields = "animal_id, name, gender, shelter_profile_url"
        if extra_fields:
            select_fields += ", " + ", ".join(extra_fields)

        adoptable_resp = (
            self.client.table("active_dogs")
            .select(select_fields)
            .eq("shelter_id", shelter_id)
            .execute()
        )
        adoptable_dogs = {row["animal_id"]: row for row in adoptable_resp.data}
        adoptable_ids = list(adoptable_dogs.keys())

        if not adoptable_ids:
            return []

        # Get update times — fetch in chunks to bypass Supabase 1000-row limit
        updated_times = {}
        for i in range(0, len(adoptable_ids), 100):
            chunk = adoptable_ids[i : i + 100]
            animals_res = (
                self.client.table("animals")
                .select("animal_id, updated_at")
                .in_("animal_id", chunk)
                .execute()
            )
            for row in animals_res.data:
                if row.get("updated_at"):
                    updated_times[row["animal_id"]] = row["updated_at"]

        # Sort: oldest-updated first, never-scraped dogs get "" (sorted first)
        adoptable_ids.sort(key=lambda aid: updated_times.get(aid, ""))
        top_ids = adoptable_ids[:limit]

        results = []
        for aid in top_ids:
            dog = adoptable_dogs[aid]
            url = dog.get("shelter_profile_url")
            if not url and fallback_url_fn:
                url = fallback_url_fn(aid)
            result = {
                "url": url,
                "animal_id": aid,
                "name": dog.get("name"),
                "gender": dog.get("gender"),
            }
            # Include any extra fields
            if extra_fields:
                for field in extra_fields:
                    result[field] = dog.get(field)
            results.append(result)
        return results
