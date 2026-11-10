"""
SFSPCA (San Francisco SPCA, San Francisco CA) — Inventory Scraper

The dogs page (https://www.sfspca.org/adoptions/dogs/) renders its grid
client-side from a custom WordPress REST endpoint:

    GET https://www.sfspca.org/wp-json/sfspca/v1/adoption
        ?per_page=..&page=..
        &ignored-terms[sfspca-adoption-species][]=55   (55 = cats)
        &ignored-terms[sfspca-adoption-site][]=59      (site the page also hides)

We send the same request the page does (the "ignored terms" are read from the
page's own sfspcaUserContent config when available, so if the site changes them
we follow), and full-replace this shelter's active_dogs rows. Every profile is
also checked for the `sfspca-adoption-species-dog` class by profiles.py, so a
non-dog that slips through is removed.

IDs: animal_id = "SFSPCA-{id}" where {id} is the PetPoint animal ID in the
permalink https://www.sfspca.org/sfspca-adoption/{id}/.

The site is behind Cloudflare, which rejects bare user agents — keep the full
browser-like headers below.

No Playwright needed. Runs via APScheduler.
"""

import html
import json
import logging
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests

from jobs.lib.db import get_supabase_client, now_iso, record_run_finish, record_run_start

SHELTER_ID = "SFSPCA"
SHELTER_NAME = "San Francisco SPCA"
CITY = "San Francisco"
STATE = "CA"

LISTING_URL = "https://www.sfspca.org/adoptions/dogs/"
API_URL = "https://www.sfspca.org/wp-json/sfspca/v1/adoption"
PERMALINK_RE = re.compile(r"^https?://(?:www\.)?sfspca\.org/sfspca-adoption/(\d+)/?")

# Fallback if the page config can't be read: hide cats (55) and site 59, exactly
# as the dogs page does today.
DEFAULT_IGNORED_TERMS = {"sfspca-adoption-species": ["55"], "sfspca-adoption-site": ["59"]}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": LISTING_URL,
}
API_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

PAGE_SIZE = 100
MAX_PAGES = 10
# SF SPCA typically lists 30-40 dogs; fewer than this means something broke.
MIN_EXPECTED_DOGS = 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helpers (shared with profiles.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def http_get(url: str, *, api: bool = False, params=None, retries: int = 2) -> requests.Response:
    """GET with browser-like headers and a short backoff on Cloudflare 403/429/5xx."""
    headers = API_HEADERS if api else HEADERS
    resp = None
    for attempt in range(retries + 1):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code not in (403, 429, 500, 502, 503, 504) or attempt == retries:
            break
        time.sleep(5 * (attempt + 1))
    return resp


def animal_id_from_url(url: str) -> Optional[str]:
    m = PERMALINK_RE.match(url or "")
    return f"{SHELTER_ID}-{m.group(1)}" if m else None


def clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(raw or "")).strip()


def format_weight(text: str) -> str:
    """'92 lbs; 6 oz' → '92.4 lbs'; '0 lb; 14 oz' → '0.9 lbs'; '92lbs' → '92 lbs'."""
    text = (text or "").lower()
    lbs = re.search(r"(\d+(?:\.\d+)?)\s*lbs?", text)
    oz = re.search(r"(\d+(?:\.\d+)?)\s*oz", text)
    if not lbs and not oz:
        return ""
    total = (float(lbs.group(1)) if lbs else 0.0) + (float(oz.group(1)) / 16 if oz else 0.0)
    if total <= 0:
        return ""
    return f"{round(total, 1):g} lbs"


def format_age(text: str) -> str:
    """'4 years 5 months old' → '4 years 5 months'."""
    return re.sub(r"\s+old\s*$", "", (text or "").strip(), flags=re.I)


def parse_stats(label: str) -> Dict[str, str]:
    """API statsLabel '5 years old, Male, 92lbs' → age / gender / weight."""
    out = {"age": "", "gender": "", "weight": ""}
    for part in (p.strip() for p in (label or "").split(",")):
        if re.fullmatch(r"(?i)male|female", part):
            out["gender"] = part.capitalize()
        elif re.search(r"(?i)\b(lbs?|oz)\b|\dlbs", part):
            out["weight"] = format_weight(part)
        elif re.search(r"(?i)\b(year|month|week|day)s?\b", part):
            out["age"] = format_age(part)
    return out


def ignored_terms_from_page() -> Dict[str, List[str]]:
    """Read the dogs page's own 'ignoredTerms' config (which species/sites it hides)."""
    try:
        resp = http_get(LISTING_URL)
        resp.raise_for_status()
        m = re.search(r'"ignoredTerms":(\{[^{}]*\})', resp.text)
        if m:
            terms = json.loads(m.group(1))
            if terms.get("sfspca-adoption-species"):
                return terms
    except Exception as exc:  # fall back to known values
        logging.warning(f"Could not read ignoredTerms from {LISTING_URL}: {exc}")
    return DEFAULT_IGNORED_TERMS


def fetch_dog_items() -> List[Dict[str, Any]]:
    """All items the dogs page would show (title, permalink, thumb, statsLabel)."""
    ignored = ignored_terms_from_page()
    items: List[Dict[str, Any]] = []
    page, max_pages = 1, 1
    while page <= max_pages and page <= MAX_PAGES:
        params = [("per_page", PAGE_SIZE), ("page", page), ("order", "ASC"), ("orderby", "")]
        for taxonomy, term_ids in ignored.items():
            for term_id in term_ids:
                params.append((f"ignored-terms[{taxonomy}][]", term_id))
        resp = http_get(API_URL, api=True, params=params)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("items") or [])
        max_pages = int((data.get("pagination") or {}).get("maxPages") or 1)
        page += 1
        if page <= max_pages:
            time.sleep(2)
    return items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Inventory job
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_rows(items: List[Dict[str, Any]], scraped_at: str) -> List[Dict[str, Any]]:
    rows, seen = [], set()
    for item in items:
        url = (item.get("permalink") or "").strip()
        aid = animal_id_from_url(url)
        if not aid or aid in seen:
            continue
        seen.add(aid)
        stats = parse_stats(item.get("statsLabel") or item.get("stats") or "")
        rows.append({
            "animal_id": aid,
            "name": clean_name(item.get("title") or ""),
            "gender": stats["gender"] or None,
            "age": stats["age"],
            "weight": stats["weight"],
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": url,
            "scraped_at": scraped_at,
            "shelter_id": SHELTER_ID,
        })
    return rows


def scrape_inventory() -> List[Dict[str, Any]]:
    """Fetch SF SPCA's adoptable dogs and full-replace active_dogs."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_sfspca_inventory")
    logging.info("Starting SFSPCA inventory scrape...")

    try:
        items = fetch_dog_items()
        rows = build_rows(items, now_iso())
        logging.info(f"Fetched {len(items)} items → {len(rows)} dogs")

        if len(rows) < MIN_EXPECTED_DOGS:
            # API change / Cloudflare block — keep the previous inventory rather
            # than wiping it (and cascading deletes of favorites/chats).
            raise RuntimeError(
                f"Parsed {len(rows)} dogs for {SHELTER_ID} from {len(items)} API items "
                f"— API may have changed or request was blocked"
            )

        logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
        client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()
        logging.info(f"Inserting {len(rows)} dogs into active_dogs...")
        for i in range(0, len(rows), 100):
            client.table("active_dogs").insert(rows[i:i + 100]).execute()

        record_run_finish(client, run_id, "success", notes=json.dumps({"scraped_count": len(rows)}))
        logging.info("Done.")
        return rows

    except Exception as exc:
        logging.error(f"Inventory scrape failed: {exc}")
        record_run_finish(client, run_id, "error", notes=str(exc))
        raise


if __name__ == "__main__":
    scrape_inventory()
