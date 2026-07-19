#!/usr/bin/env python3
"""
Scrape NYC ACC dog tiles from https://nycacc.app.

Why this version is different:
- nycacc.app is a Flutter CanvasKit app, so the dog cards are painted on a canvas.
  BeautifulSoup and normal DOM scraping will not see the card text.
- This script injects a fetch/XHR interceptor before the app loads and captures the
  GraphQL responses that power the app.
- It then extracts dog records from the captured GraphQL JSON and writes a CSV.

Install:
    pip install playwright
    playwright install chromium

Run:
    python scrape_nycacc_dogs_v3.py --headed --out nycacc_dogs.csv

If the filter click is flaky, skip it and let the script browse all animals, then
filter to dogs from the API payload:
    python scrape_nycacc_dogs_v3.py --headed --skip-dog-filter --out nycacc_dogs.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import os

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish as _record_run_finish


def record_run_finish(client, run_id: int, status: str, notes_dict: dict) -> None:
    """Wrapper to match the original signature that takes a notes_dict."""
    _record_run_finish(client, run_id, status, notes=json.dumps(notes_dict))


BASE_URL = "https://nycacc.app/#/browse"
PROFILE_URL_TEMPLATE = "https://nycacc.app/#/browse/{animal_id}"
GRAPHQL_HOST_RE = re.compile(r"pets\.mcgilldevtech\.com/(graphql|token)", re.I)
DOG_RE = re.compile(r"\bdogs?\b", re.I)

FIELDS = [
    "animal_id",
    "profile_url",
    "name",
    "species",
    "breed",
    "gender",
    "age",
    "weight",
    "status",
    "location",
    "image_url",
    "source",
    "scraped_at",
]

# Common exact-ish ID field names. We deliberately do not scan arbitrary JSON blobs
# anymore because that produced false IDs from Firebase project/token data.
ID_KEY_RE = re.compile(
    r"(^|[_.-])(id|animal_?id|animal_?number|pet_?id|pet_?number|shelter_?buddy_?id|record_?id)$",
    re.I,
)
NAME_KEY_RE = re.compile(r"(^|[_.-])(name|animal_?name|pet_?name)$", re.I)
SPECIES_KEY_RE = re.compile(r"species|animal.?type|pet.?type", re.I)
BREED_KEY_RE = re.compile(r"breed", re.I)
GENDER_KEY_RE = re.compile(r"(^|[_.-])(gender|sex)$", re.I)
AGE_KEY_RE = re.compile(r"(^|[_.-])age($|[_.-])|age.?text|age.?display", re.I)
WEIGHT_KEY_RE = re.compile(r"weight", re.I)
STATUS_KEY_RE = re.compile(r"status|availability|stage", re.I)
LOCATION_KEY_RE = re.compile(r"location|care.?center|shelter|borough|kennel", re.I)
IMAGE_KEY_RE = re.compile(r"image|photo|picture|thumbnail|media", re.I)

BAD_NAME_KEY_RE = re.compile(r"file|image|photo|picture|user|org|organization|shelter|location|breed|species", re.I)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def looks_like_numeric_animal_id(value: Any) -> str:
    s = clean(value)
    if not s:
        return ""

    # IDs seen in the app are numeric and generally six digits, but keep a little
    # room on either side in case older records differ.
    m = re.fullmatch(r"#?([0-9]{5,8})", s)
    if m:
        return m.group(1)

    # Sometimes IDs arrive in a display string like "Crown (256087)".
    m = re.search(r"\b([0-9]{5,8})\b", s)
    if m:
        return m.group(1)

    return ""


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def flatten_json(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                out.update(flatten_json(v, key))
            else:
                out[key] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}.{i}" if prefix else str(i)
            if isinstance(v, (dict, list)):
                out.update(flatten_json(v, key))
            else:
                out[key] = v

    return out


def iter_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def iter_lists(obj: Any) -> Iterable[List[Any]]:
    if isinstance(obj, list):
        yield obj
        for v in obj:
            yield from iter_lists(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_lists(v)


def first_matching(flat: Dict[str, Any], key_re: re.Pattern, *, skip_re: Optional[re.Pattern] = None) -> str:
    # Prefer shorter/more direct keys first. Flattened paths like data.pets.0.name
    # are fine; very long nested paths are usually less reliable.
    for key, value in sorted(flat.items(), key=lambda kv: (len(kv[0]), kv[0])):
        if skip_re and skip_re.search(key):
            continue
        if key_re.search(key) and is_scalar(value):
            val = clean(value)
            if val:
                return val
    return ""


def first_image(flat: Dict[str, Any]) -> str:
    preferred: List[str] = []
    fallback: List[str] = []

    for key, value in flat.items():
        if not is_scalar(value):
            continue
        s = clean(value)
        if not s.startswith("http"):
            continue
        if not re.search(r"\.(?:jpg|jpeg|png|webp)(?:[/?#]|$)", s, re.I) and "shelterbuddy.com/storage/image" not in s:
            continue
        if IMAGE_KEY_RE.search(key):
            preferred.append(s)
        else:
            fallback.append(s)

    return preferred[0] if preferred else (fallback[0] if fallback else "")


def normalize_gender(value: str) -> str:
    v = clean(value)
    low = v.lower()
    if low in {"m", "male"}:
        return "Male"
    if low in {"f", "female"}:
        return "Female"
    return v


def normalize_weight(value: str) -> str:
    v = clean(value)
    if not v:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        return f"{v} lbs"
    return v


def object_has_animal_shape(flat: Dict[str, Any]) -> bool:
    has_name = bool(first_matching(flat, NAME_KEY_RE, skip_re=BAD_NAME_KEY_RE))
    has_species = bool(first_species(flat))
    has_gender = bool(first_matching(flat, GENDER_KEY_RE))
    has_age = bool(first_matching(flat, AGE_KEY_RE))
    has_weight = bool(first_matching(flat, WEIGHT_KEY_RE))
    has_breed = bool(first_matching(flat, BREED_KEY_RE))
    has_image = bool(first_image(flat))

    return has_name and sum(bool(x) for x in [has_species, has_gender, has_age, has_weight, has_breed, has_image]) >= 1


def get_animal_id(flat: Dict[str, Any]) -> str:
    candidates: List[Tuple[int, str, str]] = []

    for key, value in flat.items():
        key_leaf = key.split(".")[-1]
        if ID_KEY_RE.search(key_leaf) or ID_KEY_RE.search(key):
            animal_id = looks_like_numeric_animal_id(value)
            if animal_id:
                # Prefer animal/pet-specific keys over generic id.
                score = 0
                if re.search(r"animal|pet|shelter", key, re.I):
                    score -= 10
                score += len(key)
                candidates.append((score, key, animal_id))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0])
    return candidates[0][2]


def first_species(flat: Dict[str, Any]) -> str:
    vals = []
    for key, value in flat.items():
        if SPECIES_KEY_RE.search(key) and is_scalar(value):
            val = clean(value)
            if not val:
                continue
            # Prefer human-readable species labels over numeric/internal ids.
            if re.fullmatch(r"[0-9]+", val):
                continue
            vals.append((0 if DOG_RE.search(val) else 1, len(key), val))
    vals.sort(key=lambda x: (x[0], x[1]))
    return vals[0][2] if vals else ""


def record_from_graphql_object(obj: Dict[str, Any], *, assume_dog_view: bool, include_unknown_species: bool) -> Optional[Dict[str, str]]:
    flat = flatten_json(obj)

    if not object_has_animal_shape(flat):
        return None

    animal_id = get_animal_id(flat)
    if not animal_id:
        return None

    name = first_matching(flat, NAME_KEY_RE, skip_re=BAD_NAME_KEY_RE)
    species = first_species(flat)
    breed = first_matching(flat, BREED_KEY_RE)
    gender = normalize_gender(first_matching(flat, GENDER_KEY_RE))
    age = first_matching(flat, AGE_KEY_RE)
    weight = normalize_weight(first_matching(flat, WEIGHT_KEY_RE))
    status = first_matching(flat, STATUS_KEY_RE)
    location = first_matching(flat, LOCATION_KEY_RE)
    image_url = first_image(flat)

    if not species and assume_dog_view:
        species = "Dog"

    if species and not DOG_RE.search(species):
        return None

    # If no species field exists, only keep it when the UI was successfully filtered
    # to dog view or the caller explicitly allows unknown species.
    if not species and not assume_dog_view and not include_unknown_species:
        return None

    return {
        "animal_id": animal_id,
        "profile_url": PROFILE_URL_TEMPLATE.format(animal_id=animal_id),
        "name": name,
        "species": species or "Dog",
        "breed": breed,
        "gender": gender,
        "age": age,
        "weight": weight,
        "status": status,
        "location": location,
        "image_url": image_url,
        "source": "graphql",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_record(records: Dict[str, Dict[str, str]], record: Dict[str, str]) -> None:
    animal_id = clean(record.get("animal_id"))
    if not animal_id:
        return

    if animal_id not in records:
        records[animal_id] = {field: clean(record.get(field)) for field in FIELDS}
        return

    existing = records[animal_id]
    for field in FIELDS:
        if not clean(existing.get(field)) and clean(record.get(field)):
            existing[field] = clean(record.get(field))


def parse_json_maybe(text: str) -> Optional[Any]:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def parse_records_from_api_logs(logs: List[Dict[str, Any]], *, assume_dog_view: bool, include_unknown_species: bool = False) -> Dict[str, Dict[str, str]]:
    records: Dict[str, Dict[str, str]] = {}

    for log in logs:
        url = clean(log.get("url"))
        if "/graphql" not in url:
            continue

        text = clean(log.get("responseText"))
        data = parse_json_maybe(text)
        if data is None:
            continue

        for obj in iter_dicts(data):
            rec = record_from_graphql_object(obj, assume_dog_view=assume_dog_view, include_unknown_species=include_unknown_species)
            if rec:
                merge_record(records, rec)

    return records


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field)) for field in FIELDS})


FETCH_INTERCEPTOR_JS = r"""
(() => {
  if (window.__ACC_INTERCEPTOR_INSTALLED) return;
  window.__ACC_INTERCEPTOR_INSTALLED = true;
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
            transport: 'fetch',
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
            transport: 'fetch',
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
              transport: 'xhr',
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


async def wait_quietly(page, timeout_ms: int = 5000) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


async def get_api_logs(page) -> List[Dict[str, Any]]:
    try:
        logs = await page.evaluate("() => window.__ACC_API_LOGS || []")
        return logs if isinstance(logs, list) else []
    except Exception:
        return []


async def get_api_log_count(page) -> int:
    try:
        return int(await page.evaluate("() => (window.__ACC_API_LOGS || []).length"))
    except Exception:
        return 0


async def enable_flutter_accessibility(page) -> bool:
    # Flutter CanvasKit renders text to a canvas. Enabling semantics can make some
    # labels/buttons available to Playwright. This is useful for the optional filter.
    try:
        placeholder = page.locator('flt-semantics-placeholder[aria-label="Enable accessibility"]')
        if await placeholder.count():
            await placeholder.first.click(timeout=2000)
            await page.wait_for_timeout(1000)
            return True
    except Exception:
        pass

    try:
        await page.get_by_label(re.compile("Enable accessibility", re.I)).click(timeout=2000)
        await page.wait_for_timeout(1000)
        return True
    except Exception:
        return False


async def click_by_text_or_label(page, pattern: str, timeout_ms: int = 2000) -> bool:
    regex = re.compile(pattern, re.I)
    attempts = [
        lambda: page.get_by_role("button", name=regex).first.click(timeout=timeout_ms),
        lambda: page.get_by_label(regex).first.click(timeout=timeout_ms),
        lambda: page.get_by_text(regex).first.click(timeout=timeout_ms),
    ]
    for attempt in attempts:
        try:
            await attempt()
            await page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    return False


async def try_apply_dog_filter(page, width: int, height: int) -> bool:
    """Best effort only. The scraper does not require this if species is present in API."""
    await enable_flutter_accessibility(page)

    # If the Dog chip already exists, assume we are filtered.
    try:
        if await page.get_by_text(re.compile(r"^\s*Dog\s*[x×]?\s*$", re.I)).count():
            return True
    except Exception:
        pass

    opened = await click_by_text_or_label(page, r"^\s*Filters\s*$", timeout_ms=1800)

    # Coordinate fallback: in the large viewport, the Filters button is top-right.
    if not opened:
        try:
            await page.mouse.click(width - 70, 30)
            await page.wait_for_timeout(1200)
            opened = True
        except Exception:
            opened = False

    if not opened:
        return False

    await enable_flutter_accessibility(page)

    # Try semantic/text click first.
    dog_clicked = await click_by_text_or_label(page, r"^\s*Dog\s*$", timeout_ms=1800)

    # Last-ditch coordinate guesses for a right-side/bottom modal filter panel.
    # These are intentionally only used after text/semantics fail.
    if not dog_clicked:
        guesses = [
            (width - 360, 190),
            (width - 300, 235),
            (width - 260, 280),
            (width // 2, height // 2),
        ]
        for x, y in guesses:
            try:
                await page.mouse.click(x, y)
                await page.wait_for_timeout(600)
                # Don't know whether it worked yet; continue to Apply/Done.
                dog_clicked = True
                break
            except Exception:
                pass

    # Try to apply/close the filter modal. Some versions auto-apply.
    for label in [r"^\s*Apply\s*$", r"Show Results", r"^\s*Done\s*$", r"^\s*Search\s*$", r"^\s*Close\s*$"]:
        if await click_by_text_or_label(page, label, timeout_ms=1200):
            await page.wait_for_timeout(2000)
            return dog_clicked

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    await page.wait_for_timeout(1500)
    return dog_clicked


async def scroll_page(page, pixels: int) -> None:
    # Flutter CanvasKit usually responds to mouse wheel events, not DOM scrollTop.
    try:
        await page.mouse.move(1000, 700)
        await page.mouse.wheel(0, pixels)
    except Exception:
        pass

    # Backup for non-canvas contexts.
    try:
        await page.evaluate("(pixels) => window.scrollBy(0, pixels)", pixels)
    except Exception:
        pass


async def main_async(args: argparse.Namespace) -> int:
    """Legacy Playwright-based scraper. Kept for manual/debug use with --headed."""
    raise NotImplementedError(
        "The Playwright-based inventory scraper has been replaced by main(). "
        "Use main() for production. Run with --headed for manual debugging only."
    )


# ── Direct API-based inventory (production path) ────────────────────

import requests
import uuid

GRAPHQL_URL = "https://pets.mcgilldevtech.com/graphql"
TOKEN_URL = "https://pets.mcgilldevtech.com/token"
API_KEY = "jKbOSNYtJn5qhYbsv9IKL6OEt7etN6jcALlerH82"
PROFILE_URL_TEMPLATE_V2 = "https://nycacc.app/#/browse/{native_id}"

ACC_FEED_QUERY = """
query ACCGetFeed {
  feed {
    __typename
    updated
    pets {
      id name age type species link gender weight location locationInShelter photos intakeDate
    }
  }
}
""".strip()


def fetch_acc_token() -> str:
    """Get a bearer token from the ACC API."""
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "x-api-key": API_KEY,
        },
        json={
            "deviceId": str(uuid.uuid4()),
            "organization": "nycacc",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("token") or ""
    if not token:
        raise RuntimeError(f"No token in response: {list(data.keys())}")
    return token


def fetch_acc_feed(token: str) -> list[dict]:
    """Fetch all pets from the ACC GraphQL feed."""
    resp = requests.post(
        GRAPHQL_URL,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json; charset=UTF-8",
            "apollographql-client-name": "ACC Web",
            "x-api-key": API_KEY,
            "authorization": f"Bearer {token}",
        },
        json={"query": ACC_FEED_QUERY},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    feed = data.get("data", {}).get("feed", {})
    pets = feed.get("pets", [])
    if not isinstance(pets, list):
        raise RuntimeError(f"Unexpected feed shape: {list(data.keys())}")
    return pets


def main():
    """Direct API-based inventory scraper for NYCACC."""
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_nycacc_inventory")

    try:
        print("Fetching ACC API token...")
        token = fetch_acc_token()

        print("Fetching ACC feed...")
        all_pets = fetch_acc_feed(token)
        dogs = [
            p for p in all_pets
            if (p.get("species") or p.get("type") or "").lower() == "dog"
        ]
        print(f"Total pets: {len(all_pets)}, Dogs: {len(dogs)}")

        if len(dogs) == 0:
            notes = {"scraped_count": 0, "total_pets": len(all_pets)}
            record_run_finish(client, run_id, "failed", notes)
            raise RuntimeError(
                f"NYCACC inventory: API returned {len(all_pets)} total pets but 0 dogs. "
                f"This likely indicates a site/API change."
            )

        # Map to active_dogs format
        db_rows = []
        for pet in dogs:
            name = pet.get("name", "")
            if name:
                name = name.replace("*", "").strip().title()

            native_id = str(pet.get("id", ""))
            db_rows.append({
                "animal_id": f"NYCACC-{native_id}",
                "name": name,
                "gender": pet.get("gender"),
                "age": pet.get("age"),
                "weight": pet.get("weight"),
                "city": "NYC",
                "state": "NY",
                "shelter_name": "Animal Care Centers of NYC",
                "shelter_profile_url": PROFILE_URL_TEMPLATE_V2.format(native_id=native_id),
                "scraped_at": now_iso(),
                "shelter_id": "NYCACC",
            })

        print(f"Performing full replace of {len(db_rows)} NYCACC dogs in active_dogs...")
        client.table("active_dogs").delete().eq("shelter_id", "NYCACC").execute()
        for chunk_start in range(0, len(db_rows), 100):
            chunk = db_rows[chunk_start:chunk_start + 100]
            client.table("active_dogs").insert(chunk).execute()

        notes = {"scraped_count": len(db_rows)}
        record_run_finish(client, run_id, "success", notes)
        print(f"Done. Wrote {len(db_rows)} NYCACC dogs.")

    except Exception:
        # If record_run_finish wasn't called yet (i.e. unexpected exception),
        # the scrape_runs row will stay as "running" — the scheduler's
        # _job_listener will record the failure separately.
        raise


if __name__ == "__main__":
    main()

