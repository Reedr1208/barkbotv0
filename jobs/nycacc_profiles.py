#!/usr/bin/env python3
"""
Scrape NYC ACC profile details for one or more animal profile URLs.

Why this uses Playwright:
    nycacc.app is a Flutter/CanvasKit app. The visible profile text is painted
    onto a canvas, so BeautifulSoup/DOM scraping will not see the profile fields.
    This script loads the app, captures its GraphQL responses, and then selects
    the exact pet whose native ID matches the URL/id you requested.

Install:
    pip install playwright
    playwright install chromium

Examples:
    python scrape_nycacc_profile_v2.py --url https://nycacc.app/#/browse/11125 --out nycacc_profile.csv

    python scrape_nycacc_profile_v2.py \
      --url https://nycacc.app/#/browse/11125 \
      --url https://nycacc.app/#/browse/33504 \
      --url https://nycacc.app/#/browse/88498 \
      --url https://nycacc.app/#/browse/107337 \
      --out nycacc_profiles.csv

Output fields:
    animal_id,url,located_at,weight,age,description
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import os
import hashlib
import mimetypes
from urllib.parse import urlparse
import requests
from supabase import create_client

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
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


def extension_from_response_or_url(response: requests.Response, image_url: str) -> str:
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(content_type)

    if not ext:
        ext = Path(urlparse(image_url).path).suffix

    if not ext:
        ext = ".jpg"

    if ext == ".jpe":
        ext = ".jpg"

    return ext


def download_image_bytes(image_url: str) -> Tuple[bytes, str]:
    response = requests.get(image_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    ext = extension_from_response_or_url(response, image_url)
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
        if current is None:
            payload["created_at"] = now_iso()

        self.client.table("animals").upsert(payload, on_conflict="animal_id").execute()
        return change_type
    
    def get_least_recently_updated_nycacc_dogs(self, limit: int = DOGS_PER_RUN) -> List[Dict[str, str]]:
        # Get all currently adoptable dogs for NYCACC
        adoptable_resp = self.client.table("active_dogs").select("animal_id, name, gender").eq("shelter_id", "NYCACC").execute()
        adoptable_dogs = {row["animal_id"]: row for row in adoptable_resp.data}
        adoptable_ids = list(adoptable_dogs.keys())

        if not adoptable_ids:
            return []

        # Get the update times for dogs already in the animals table
        animals_resp = self.client.table("animals").select("animal_id, updated_at").execute()
        updated_times = {row["animal_id"]: row["updated_at"] for row in animals_resp.data if row["updated_at"]}

        def get_time(aid: str):
            return updated_times.get(aid, "")

        adoptable_ids.sort(key=get_time)
        top_ids = adoptable_ids[:limit]
        
        # NYCACC animal_id format: NYCACC-12345
        dogs = []
        for aid in top_ids:
            numeric_id = aid.replace("NYCACC-", "")
            dogs.append({
                "animal_id": aid,
                "numeric_id": numeric_id,
                "url": f"https://nycacc.app/#/browse/{numeric_id}",
                "name": adoptable_dogs[aid].get("name"),
                "gender": adoptable_dogs[aid].get("gender")
            })
        return dogs




PROFILE_URL_TEMPLATE = "https://nycacc.app/#/browse/{native_id}"
LOCATED_AT = "Animal Care Centers of NYC"
GRAPHQL_URL = "https://pets.mcgilldevtech.com/graphql"
GRAPHQL_OR_API_RE = re.compile(r"pets\.mcgilldevtech\.com/(graphql|token)", re.I)
GRAPHQL_RE = re.compile(r"pets\.mcgilldevtech\.com/graphql", re.I)
NATIVE_ID_RE = re.compile(r"(?:#/browse/|/browse/|browse%2F)(\d{4,9})|\b(\d{4,9})\b", re.I)
FIELDS = ["animal_id", "url", "located_at", "weight", "age", "description"]

ACC_FEED_QUERY = """
fragment ACCPetFragment on Pet {
  id
  name
  age
  type
  species
  link
  gender
  summaryHtml
  weight
  location
  locationInShelter
  photos
  youTubeIds
  intakeDate
}
query ACCGetFeed {
  feed {
    __typename
    updated
    pets {
      ...ACCPetFragment
    }
  }
}
""".strip()

ADOPETS_STATUS_QUERY = """
query ACCAdopetsStatus($id: ID!) {
  adopetStatus(id: $id){
    link
  }
}
""".strip()

DEFAULT_GRAPHQL_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json; charset=UTF-8",
    "apollographql-client-name": "ACC Web",
    # Public app key observed in the nycacc.app browser request. The script
    # prefers captured headers when available, but this fallback helps the
    # browser-side manual feed request work if the header is not exposed.
    "x-api-key": "jKbOSNYtJn5qhYbsv9IKL6OEt7etN6jcALlerH82",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_native_id(value: str) -> str:
    text = clean(value)
    if not text:
        return ""
    for m in NATIVE_ID_RE.finditer(text):
        for group in m.groups():
            if group and group.isdigit():
                return group
    return ""


def profile_url(native_id: str) -> str:
    return PROFILE_URL_TEMPLATE.format(native_id=native_id)


def parse_json_maybe(text: Any) -> Optional[Any]:
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        return None


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dicts(value)


def html_to_text(value: Any) -> str:
    """Convert the profile summaryHtml into readable plain text."""
    s = "" if value is None else str(value)
    if not s.strip():
        return ""

    s = html.unescape(s)
    # Preserve likely paragraph/list boundaries before removing tags.
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", s)
    s = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)

    # Clean whitespace while keeping paragraph breaks somewhat readable.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def normalize_weight(value: Any) -> str:
    v = clean(value)
    if not v:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        return f"{v} lbs"
    return v


def normalize_age(value: Any) -> str:
    return clean(value)


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    s = clean(value)
    if not s:
        return None
    try:
        # Python accepts +00:00 but not Z on older versions.
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_date(value: Any) -> str:
    dt = parse_iso_datetime(value)
    if not dt:
        return clean(value)
    return dt.date().isoformat()


def calculate_days_in_care(intake_date: Any, as_of: Any = None) -> str:
    intake = parse_iso_datetime(intake_date)
    if not intake:
        return ""

    end = parse_iso_datetime(as_of) if as_of else datetime.now(timezone.utc)
    if not end:
        end = datetime.now(timezone.utc)

    seconds = (end - intake).total_seconds()
    if seconds < 0:
        return "0"

    # The ACC UI appears to round partial days upward. Example from artifacts:
    # 2026-05-28 06:22 to 2026-06-05 19:00 displays as 9 days.
    return str(max(0, int(math.ceil(seconds / 86400))))


def get_feed_from_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    # Normal GraphQL response: {"data": {"feed": {...}}}
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("feed"), dict):
        return data["feed"]

    # Debug/best-profile object might already be the feed root.
    if isinstance(payload.get("pets"), list):
        return payload

    return None


def pet_matches_id(pet: Any, native_id: str) -> bool:
    if not isinstance(pet, dict):
        return False
    return clean(pet.get("id")).lstrip("#") == native_id


def find_pet_in_payloads(payloads: List[Any], native_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Return the exact pet object matching native_id, plus feed.updated when known.

    Important: the feed response contains hundreds of pets. Do NOT flatten the
    whole feed as if it were one profile; that is what caused bios from many
    animals to be clumped into one CSV row.
    """
    # First, search actual feed responses and select from feed.pets.
    for payload in payloads:
        feed = get_feed_from_payload(payload)
        if not feed:
            continue
        updated = clean(feed.get("updated"))
        pets = feed.get("pets")
        if isinstance(pets, list):
            for pet in pets:
                if pet_matches_id(pet, native_id):
                    return pet, updated

    # Fallback: search any nested dict that itself looks like a pet record.
    for payload in payloads:
        for obj in iter_dicts(payload):
            if not pet_matches_id(obj, native_id):
                continue
            if any(k in obj for k in ["name", "age", "weight", "summaryHtml", "species", "type"]):
                return obj, ""

    return None, ""


def extract_adopets_link(payloads: List[Any]) -> str:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        data = payload.get("data")
        if isinstance(data, dict):
            status = data.get("adopetStatus") or data.get("adopetsStatus")
            if isinstance(status, dict):
                link = clean(status.get("link"))
                if link:
                    return link
    return ""


def list_to_pipe(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(clean(x) for x in value if clean(x))
    return clean(value)


def build_description(pet: Optional[Dict[str, Any]], native_id: str, feed_updated: str = "", adopets_link: str = "", *, include_photo_urls: bool = False) -> str:
    if not pet:
        return ""

    lines: List[str] = []

    def add(label: str, value: Any) -> None:
        val = clean(value)
        if val:
            lines.append(f"{label}: {val}")

    add("Name", pet.get("name"))
    add("Native ID", pet.get("id"))
    add("Species", pet.get("species") or pet.get("type"))
    add("Gender", pet.get("gender"))
    add("Location", pet.get("location"))
    add("Room", pet.get("locationInShelter"))

    intake = pet.get("intakeDate")
    add("Intake Date", fmt_date(intake))

    days_in_care = calculate_days_in_care(intake, feed_updated)
    add("Days in Care", days_in_care)

    if feed_updated:
        add("ACC Feed Updated", feed_updated)

    if adopets_link:
        add("Adoption Application Link", adopets_link)

    you_tube_ids = pet.get("youTubeIds")
    if isinstance(you_tube_ids, list) and you_tube_ids:
        add("YouTube IDs", list_to_pipe(you_tube_ids))

    photos = pet.get("photos")
    if isinstance(photos, list) and photos:
        add("Photo Count", str(len(photos)))
        if include_photo_urls:
            add("Photo URLs", list_to_pipe(photos))

    summary = html_to_text(pet.get("summaryHtml"))
    if summary:
        # Bio can be long. Keep it labeled and readable.
        lines.append(f"Bio/Summary: {summary}")

    # Include any new scalar top-level fields the schema may add later, unless
    # already represented above or captured by dedicated CSV columns.
    already = {
        "id", "name", "age", "weight", "type", "species", "link", "gender",
        "summaryHtml", "location", "locationInShelter", "photos", "youTubeIds", "intakeDate",
        "__typename",
    }
    for key in sorted(pet.keys()):
        if key in already:
            continue
        value = pet.get(key)
        if isinstance(value, (dict, list)):
            continue
        val = clean(value)
        if val:
            label = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key)
            label = re.sub(r"[_-]+", " ", label).strip().title()
            lines.append(f"{label}: {val}")

    # Pipe-separated works nicely in spreadsheets while still keeping the bio as
    # one large text field.
    return " | ".join(line.replace("\r", " ").replace("\n", " ") for line in lines)


def build_output_row(pet: Optional[Dict[str, Any]], native_id: str, feed_updated: str = "", adopets_link: str = "", *, include_photo_urls: bool = False) -> Dict[str, str]:
    weight = normalize_weight(pet.get("weight") if pet else "")
    age = normalize_age(pet.get("age") if pet else "")
    description = build_description(
        pet,
        native_id,
        feed_updated=feed_updated,
        adopets_link=adopets_link,
        include_photo_urls=include_photo_urls,
    )

    return {
        "animal_id": f"NYCACC-{native_id}",
        "shelter_profile_url": profile_url(native_id),
        "shelter_name": LOCATED_AT,
        "weight": weight,
        "age": age,
        "bio": description,
        "shelter_image_url": None, # Will be set elsewhere or left none
        "more_info": "",
        "image_file": None,
        "image_public_url": None,
        "city": "NYC",
        "state": "NY",
        "shelter_id": "NYCACC",
    }


def logs_to_payloads(logs: List[Dict[str, Any]]) -> List[Any]:
    payloads: List[Any] = []
    for log in logs:
        if not GRAPHQL_RE.search(clean(log.get("url"))):
            continue
        data = parse_json_maybe(log.get("responseText"))
        if data is not None:
            payloads.append(data)
    return payloads


def best_headers_from_logs(logs: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extract usable GraphQL request headers from captured browser logs."""
    headers = dict(DEFAULT_GRAPHQL_HEADERS)

    wanted = {
        "authorization",
        "x-api-key",
        "apollographql-client-name",
        "apollographql-client-version",
        "accept",
        "content-type",
    }

    for log in logs:
        if not GRAPHQL_RE.search(clean(log.get("url"))):
            continue
        req_headers = log.get("requestHeaders")
        if not isinstance(req_headers, dict):
            continue
        for key, value in req_headers.items():
            lk = str(key).lower()
            if lk in wanted and clean(value):
                # Preserve conventional casing where possible.
                if lk == "content-type":
                    headers["Content-Type"] = clean(value)
                elif lk == "accept":
                    headers["Accept"] = clean(value)
                elif lk == "x-api-key":
                    headers["x-api-key"] = clean(value)
                elif lk == "authorization":
                    headers["authorization"] = clean(value)
                elif lk == "apollographql-client-name":
                    headers["apollographql-client-name"] = clean(value)
                elif lk == "apollographql-client-version":
                    headers["apollographql-client-version"] = clean(value)

    return headers


FETCH_INTERCEPTOR_JS = r"""
(() => {
  if (window.__ACC_PROFILE_INTERCEPTOR_INSTALLED) return;
  window.__ACC_PROFILE_INTERCEPTOR_INSTALLED = true;
  window.__ACC_API_LOGS = [];

  const shouldCapture = (url) => /pets\.mcgilldevtech\.com\/(graphql|token)/i.test(url || '');

  const bodyToText = async (body) => {
    try {
      if (body == null) return '';
      if (typeof body === 'string') return body;
      if (body instanceof URLSearchParams) return body.toString();
      if (body instanceof FormData) {
        const out = {};
        for (const [k, v] of body.entries()) out[k] = String(v);
        return JSON.stringify(out);
      }
      if (body instanceof Blob) return await body.text();
      if (body instanceof ArrayBuffer) return new TextDecoder().decode(body);
      if (ArrayBuffer.isView(body)) return new TextDecoder().decode(body);
      return String(body);
    } catch (e) {
      return '[unreadable body: ' + e + ']';
    }
  };

  const headersToObject = (headers) => {
    const out = {};
    try {
      if (!headers) return out;
      if (headers instanceof Headers) {
        headers.forEach((v, k) => out[k] = v);
      } else if (Array.isArray(headers)) {
        for (const [k, v] of headers) out[k] = v;
      } else if (typeof headers === 'object') {
        Object.assign(out, headers);
      }
    } catch (e) {}
    return out;
  };

  const originalFetch = window.fetch;
  window.fetch = async function(input, init) {
    let url = '';
    let method = 'GET';
    let requestBody = '';
    let requestHeaders = {};

    try {
      url = typeof input === 'string' ? input : (input && input.url) || '';
      method = (init && init.method) || (input && input.method) || 'GET';
      requestHeaders = headersToObject((init && init.headers) || (input && input.headers));

      if (shouldCapture(url)) {
        if (init && 'body' in init) {
          requestBody = await bodyToText(init.body);
        } else if (input && typeof input.clone === 'function') {
          requestBody = await input.clone().text();
        }
      }
    } catch (e) {
      requestBody = '[request capture failed: ' + e + ']';
    }

    const response = await originalFetch.apply(this, arguments);

    try {
      if (shouldCapture(url)) {
        const cloned = response.clone();
        cloned.text().then((responseText) => {
          window.__ACC_API_LOGS.push({
            source: 'browser-fetch',
            ts: new Date().toISOString(),
            url,
            method,
            status: response.status,
            requestHeaders,
            responseHeaders: headersToObject(response.headers),
            requestBody,
            responseText
          });
        }).catch((e) => {
          window.__ACC_API_LOGS.push({
            source: 'browser-fetch',
            ts: new Date().toISOString(),
            url,
            method,
            status: response.status,
            requestHeaders,
            requestBody,
            responseText: '',
            error: String(e)
          });
        });
      }
    } catch (e) {}

    return response;
  };

  const OriginalXHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function() {
    const xhr = new OriginalXHR();
    let method = 'GET';
    let url = '';
    let requestBody = '';

    const originalOpen = xhr.open;
    xhr.open = function(m, u) {
      method = m || 'GET';
      url = u || '';
      return originalOpen.apply(xhr, arguments);
    };

    const originalSend = xhr.send;
    xhr.send = function(body) {
      bodyToText(body).then(t => requestBody = t).catch(() => requestBody = '');
      xhr.addEventListener('loadend', function() {
        try {
          if (shouldCapture(url)) {
            window.__ACC_API_LOGS.push({
              source: 'browser-xhr',
              ts: new Date().toISOString(),
              url,
              method,
              status: xhr.status,
              requestHeaders: {},
              responseHeaders: {},
              requestBody,
              responseText: xhr.responseText || ''
            });
          }
        } catch (e) {}
      });
      return originalSend.apply(xhr, arguments);
    };

    return xhr;
  };
})();
"""


@dataclass
class NetworkCollector:
    logs: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[asyncio.Task] = field(default_factory=list)

    def attach(self, page) -> None:
        def on_response(response):
            task = asyncio.create_task(self.handle_response(response))
            self.tasks.append(task)

        page.on("response", on_response)

    async def drain(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.tasks.clear()

    async def handle_response(self, response) -> None:
        url = response.url
        if not GRAPHQL_OR_API_RE.search(url):
            return

        try:
            response_text = await response.text()
        except Exception as e:
            response_text = ""
            err = str(e)
        else:
            err = ""

        self.logs.append(
            {
                "source": "playwright-response",
                "ts": datetime.now(timezone.utc).isoformat(),
                "url": url,
                "method": response.request.method,
                "status": response.status,
                "requestHeaders": response.request.headers,
                "requestBody": response.request.post_data or "",
                "responseText": response_text,
                "error": err,
            }
        )


async def wait_quietly(page, timeout_ms: int = 5000) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


async def get_browser_logs(page) -> List[Dict[str, Any]]:
    try:
        logs = await page.evaluate("() => window.__ACC_API_LOGS || []")
        return logs if isinstance(logs, list) else []
    except Exception:
        return []


async def wait_for_logs(page, collector: NetworkCollector, timeout_ms: int, min_logs: int = 1) -> None:
    start = time.time()
    last_total = -1
    stable = 0
    while (time.time() - start) * 1000 < timeout_ms:
        await collector.drain()
        total = len(collector.logs) + len(await get_browser_logs(page))
        if total >= min_logs:
            if total == last_total:
                stable += 1
            else:
                stable = 0
            if stable >= 2:
                return
        last_total = total
        await page.wait_for_timeout(500)


async def combined_logs(page, collector: NetworkCollector) -> List[Dict[str, Any]]:
    await collector.drain()
    browser_logs = await get_browser_logs(page)
    combined = browser_logs + collector.logs

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for log in combined:
        key = (
            clean(log.get("url")),
            clean(log.get("requestBody"))[:1000],
            clean(log.get("responseText"))[:1000],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(log)
    return deduped


async def fetch_graphql_from_browser(page, query: str, variables: Optional[Dict[str, Any]], headers: Dict[str, str]) -> Dict[str, Any]:
    """Run a GraphQL request from inside the loaded app/browser context."""
    result = await page.evaluate(
        """
        async ({url, query, variables, headers}) => {
          try {
            const res = await fetch(url, {
              method: 'POST',
              headers,
              body: JSON.stringify({query, variables: variables || {}})
            });
            const text = await res.text();
            return {ok: res.ok, status: res.status, text};
          } catch (e) {
            return {ok: false, status: 0, text: '', error: String(e)};
          }
        }
        """,
        {"url": GRAPHQL_URL, "query": query, "variables": variables or {}, "headers": headers},
    )
    return result if isinstance(result, dict) else {"ok": False, "status": 0, "text": ""}


async def load_app_and_collect_feed(page, collector: NetworkCollector, first_native_id: str, args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], List[Any]]:
    url = profile_url(first_native_id)
    print(f"Opening {url}")

    await page.goto(url, wait_until="domcontentloaded", timeout=args.nav_timeout_ms)
    await wait_quietly(page, args.networkidle_timeout_ms)
    await page.wait_for_timeout(args.initial_wait_ms)
    await wait_for_logs(page, collector, timeout_ms=args.api_wait_ms, min_logs=1)

    # A small scroll sometimes wakes up lazy profile calls.
    for _ in range(args.scroll_rounds):
        try:
            await page.mouse.move(args.width // 2, args.height // 2)
            await page.mouse.wheel(0, args.scroll_px)
        except Exception:
            pass
        await page.wait_for_timeout(args.scroll_pause_ms)
        await wait_for_logs(page, collector, timeout_ms=2500, min_logs=1)

    logs = await combined_logs(page, collector)
    payloads = logs_to_payloads(logs)

    has_feed = any(get_feed_from_payload(p) for p in payloads)
    print(f"  captured_api_logs={len(logs)} feed_seen={has_feed}")

    if not has_feed:
        print("  Feed was not in captured traffic; requesting ACCGetFeed from the browser context...")
        headers = best_headers_from_logs(logs)
        result = await fetch_graphql_from_browser(page, ACC_FEED_QUERY, None, headers)
        manual_log = {
            "source": "manual-browser-fetch",
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": GRAPHQL_URL,
            "method": "POST",
            "status": result.get("status"),
            "requestHeaders": headers,
            "requestBody": json.dumps({"query": ACC_FEED_QUERY}, ensure_ascii=False),
            "responseText": result.get("text") or "",
            "error": result.get("error") or "",
        }
        logs.append(manual_log)
        payload = parse_json_maybe(result.get("text"))
        if payload is not None:
            payloads.append(payload)
        print(f"  manual_feed_status={result.get('status')} manual_feed_ok={bool(get_feed_from_payload(payload) if payload is not None else False)}")

    return logs, payloads


async def collect_adopets_status(page, native_id: str, logs: List[Dict[str, Any]]) -> str:
    """Optional: fetch the application link for this ID, using captured headers."""
    headers = best_headers_from_logs(logs)
    result = await fetch_graphql_from_browser(page, ADOPETS_STATUS_QUERY, {"id": native_id}, headers)
    payload = parse_json_maybe(result.get("text"))
    return extract_adopets_link([payload] if payload is not None else [])


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field)) for field in FIELDS})


def write_debug(debug_dir: Path, logs: List[Dict[str, Any]], payloads: List[Any], rows_debug: Dict[str, Dict[str, Any]]) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)

    (debug_dir / "all_api_logs.json").write_text(
        json.dumps(logs, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    graphql_logs = [log for log in logs if GRAPHQL_RE.search(clean(log.get("url")))]
    (debug_dir / "all_graphql_logs.json").write_text(
        json.dumps(graphql_logs, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    for native_id, obj in rows_debug.items():
        (debug_dir / f"{native_id}_selected_pet.json").write_text(
            json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )

    # Keep a compact list of feed IDs for troubleshooting without dumping the
    # full 2MB feed separately from the logs.
    feed_summary = []
    for payload in payloads:
        feed = get_feed_from_payload(payload)
        if not feed:
            continue
        for pet in feed.get("pets") or []:
            if isinstance(pet, dict):
                feed_summary.append({
                    "id": pet.get("id"),
                    "name": pet.get("name"),
                    "species": pet.get("species") or pet.get("type"),
                    "age": pet.get("age"),
                    "weight": pet.get("weight"),
                })
        break
    if feed_summary:
        (debug_dir / "feed_summary.json").write_text(
            json.dumps(feed_summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )


def read_urls_file(path: str) -> List[str]:
    items: List[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    store = BarkbotStore(settings)
    
    dogs = store.get_least_recently_updated_nycacc_dogs(limit=DOGS_PER_RUN)
    if not dogs:
        print("No adoptable NYCACC dogs found to scrape.")
        return 0

    dog_info = {d["numeric_id"]: d for d in dogs}
    native_ids = list(dog_info.keys())

    print(f"Scraping {len(native_ids)} NYCACC dogs.")

    if "VERCEL" in os.environ or "storage_SUPABASE_URL" in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/ms-playwright"
        os.system("python -m playwright install chromium")

    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run("cron_nycacc_profiles", len(dogs))

    start_time = time.time()
    max_time = 230  # 4 mins limit, leave some buffer

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                f"--window-size={args.width},{args.height}",
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            viewport={"width": args.width, "height": args.height},
            screen={"width": args.width, "height": args.height},
            device_scale_factor=1,
            service_workers="block",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        await context.add_init_script(FETCH_INTERCEPTOR_JS)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = await context.new_page()

        collector = NetworkCollector()
        collector.attach(page)

        try:
            logs, payloads = await load_app_and_collect_feed(page, collector, native_ids[0], args)

            for native_id in native_ids:
                if time.time() - start_time > max_time:
                    print("Reached 4-minute limit, breaking early.")
                    break
                    
                processed += 1
                pet, feed_updated = find_pet_in_payloads(payloads, native_id)
                adopets_link = ""
                if args.include_adopets_link:
                    try:
                        adopets_link = await collect_adopets_status(page, native_id, logs)
                    except Exception as e:
                        print(f"  WARNING: could not fetch adopets link for {native_id}: {e}")

                if pet is None:
                    print(f"  WARNING: no matching pet found for {native_id}")
                    errors += 1
                    # Remove from active_dogs if not found
                    aid = f"NYCACC-{native_id}"
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_not_found"}, ensure_ascii=False))
                    except Exception as e:
                        pass
                    continue
                
                # Format into Barkbot structure
                raw_row = build_output_row(
                    pet,
                    native_id,
                    feed_updated=feed_updated,
                    adopets_link=adopets_link,
                    include_photo_urls=args.include_photo_urls,
                )
                
                dog_meta = dog_info.get(native_id, {})
                record = {
                    "animal_id": raw_row["animal_id"],
                    "shelter_profile_url": raw_row["shelter_profile_url"],
                    "name": dog_meta.get("name", "Unknown"),
                    "gender": dog_meta.get("gender", "Unknown"),
                    "shelter_name": raw_row["shelter_name"],
                    "weight": raw_row["weight"],
                    "age": raw_row["age"],
                    "shelter_image_url": first_image_from_pet(pet), # Need to implement this
                    "bio": raw_row["bio"],
                    "more_info": "",
                }

                try:
                    import urllib.request
                    # Upload image
                    image_file, image_public_url = store.upload_image(record["animal_id"], record.get("shelter_image_url"))
                    if image_file and image_public_url:
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
                    print(json.dumps({"animal_id": record["animal_id"], "error": str(exc)}, ensure_ascii=False))
                    
        finally:
            await browser.close()
            
        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)

    return 0

def first_image_from_pet(pet: dict) -> str:
    photos = pet.get("photos")
    if isinstance(photos, list) and photos:
        for p in photos:
            if isinstance(p, str) and p.startswith("http"):
                return p
    return ""

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", help="Profile URL. Can be passed multiple times.")
    parser.add_argument("--id", action="append", help="Native NYC ACC numeric animal ID. Can be passed multiple times.")
    parser.add_argument("--urls-file", help="Text file with one profile URL or native ID per line.")
    parser.add_argument("--out", default="nycacc_profiles.csv")
    parser.add_argument("--debug-dir", default="nycacc_profile_debug_v2")
    parser.add_argument("--headed", action="store_true", help="Show browser window.")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--include-photo-urls", action="store_true", help="Put all photo URLs in the description field.")
    parser.add_argument("--include-adopets-link", action="store_true", help="Also fetch and include the Adoptets application link.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--nav-timeout-ms", type=int, default=90000)
    parser.add_argument("--networkidle-timeout-ms", type=int, default=10000)
    parser.add_argument("--initial-wait-ms", type=int, default=7000)
    parser.add_argument("--api-wait-ms", type=int, default=15000)
    parser.add_argument("--scroll-rounds", type=int, default=1)
    parser.add_argument("--scroll-px", type=int, default=900)
    parser.add_argument("--scroll-pause-ms", type=int, default=1200)
    return parser


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(build_arg_parser().parse_args())))
