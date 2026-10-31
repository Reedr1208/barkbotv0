"""
PAWSCO (PawsCo, Denver CO) — Inventory Scraper

PawsCo is a foster-based rescue whose WordPress site (Total theme + WPBakery)
renders every adoptable animal server-side in a single `vc_basic_grid` on
https://pawsco.org/adopt — no pagination, no Playwright needed.

Grid items carry a category term class:
    vc_grid-term-5 → Dog, vc_grid-term-4 → Cat
Each card links to https://pawsco.org/animals/meet-{slug} and has an excerpt
like "Josie<br>Beagle Mix<br>Spayed Female<br>12 years – 30 lbs".

The listing has no shelter ID, and the "Animal Number" on profile pages is
optional, so animal_id uses the WordPress post ID (stable across title/slug
edits), resolved with a cheap HEAD request per dog from the `rel=shortlink`
Link header:  animal_id = "PAWSCO-{post_id}".

Runs via APScheduler (jobs/shelter_registry.py).
"""

import json
import logging
import re
import sys
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "PAWSCO"
SHELTER_NAME = "PawsCo"
CITY = "Denver"
STATE = "CO"

LISTING_URL = "https://pawsco.org/adopt"
DOG_TERM_CLASS = "vc_grid-term-5"
PROFILE_PATH_RE = re.compile(r"^https?://(?:www\.)?pawsco\.org/animals/([^/?#]+)/?$")
# Grid tiles that aren't real animals (e.g. the "see animals coming soon" promo tile)
EXCLUDED_SLUG_RE = re.compile(r"coming-soon", re.I)

# Abort (keep the previous inventory) if a scrape returns fewer dogs than this.
# PawsCo is small (~10-20 dogs), so only guard against an empty/broken parse.
MIN_EXPECTED_DOGS = 1

# PawsCo sits behind Cloudflare, which answers bursts with HTTP 429 (and
# sometimes 403). Keep every request to pawsco.org at least this far apart.
MIN_REQUEST_INTERVAL_SECONDS = 5.0
MAX_RETRY_AFTER_SECONDS = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_last_request_at = 0.0


def polite_request(method: str, url: str, session: Optional[requests.Session] = None,
                   **kwargs) -> requests.Response:
    """GET/HEAD pawsco.org with a minimum spacing between requests and one
    Retry-After backoff on 429. Returns the final Response (caller checks status)."""
    global _last_request_at
    sender = session or requests
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", 30)
    resp = None
    for attempt in range(2):
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        resp = sender.request(method, url, **kwargs)
        if resp.status_code != 429 or attempt == 1:
            return resp
        try:
            retry_after = float(resp.headers.get("retry-after", ""))
        except ValueError:
            retry_after = 20.0
        logging.warning(f"429 from {url}; retrying in {min(retry_after, MAX_RETRY_AFTER_SECONDS):.0f}s")
        time.sleep(min(retry_after, MAX_RETRY_AFTER_SECONDS))
    return resp


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def parse_card_summary(lines: List[str]) -> Dict[str, str]:
    """Parse the card excerpt lines: name / breed / sex / "age – weight"."""
    lines = [_clean(l) for l in lines if _clean(l)]
    out = {"name": "", "gender": None, "age": "", "weight": ""}
    if not lines:
        return out
    out["name"] = lines[0]
    for line in lines[1:]:
        low = line.lower()
        if re.search(r"\bfemale\b", low):
            out["gender"] = "Female"
        elif re.search(r"\bmale\b", low):
            out["gender"] = "Male"
        if re.search(r"\b(lbs?|pounds?)\b", low) or re.search(r"\b(years?|months?|weeks?|yrs?)\b", low):
            parts = [p.strip(" .") for p in re.split(r"\s+[-–—]\s+", line)]
            for p in parts:
                pl = p.lower()
                if re.search(r"\b(lbs?|pounds?)\b", pl):
                    out["weight"] = p
                elif re.search(r"\b(years?|months?|weeks?|yrs?)\b", pl):
                    out["age"] = re.sub(r"\s+old$", "", p, flags=re.I)
    return out


def parse_listing_page(html: str) -> List[Dict]:
    """Return [{slug, url, name, gender, age, weight}] for dog tiles on the adopt page."""
    soup = BeautifulSoup(html, "html.parser")
    dogs, seen = [], set()

    for item in soup.select("div.vc_grid-item"):
        classes = item.get("class") or []
        if DOG_TERM_CLASS not in classes:
            continue

        link = item.select_one("a.vc-zone-link[href]") or item.select_one("a[href*='/animals/']")
        if not link:
            continue
        url = link["href"].strip()
        m = PROFILE_PATH_RE.match(url)
        if not m:
            continue
        slug = m.group(1)
        if EXCLUDED_SLUG_RE.search(slug) or slug in seen:
            continue
        seen.add(slug)

        # Prefer the visible excerpt; fall back to the image alt text (same content).
        lines: List[str] = []
        excerpt = item.select_one(".vc_gitem-post-data-source-post_excerpt")
        if excerpt:
            for br in excerpt.find_all("br"):
                br.replace_with("\n")
            lines = excerpt.get_text("").split("\n")
        if not any(_clean(l) for l in lines):
            img = item.select_one("img")
            lines = (img.get("alt") or "").splitlines() if img else []

        summary = parse_card_summary(lines)
        if not summary["name"]:
            title = link.get("title") or ""
            summary["name"] = _clean(re.sub(r"^meet\s+|!$", "", title, flags=re.I))

        dogs.append({"slug": slug, "url": f"https://pawsco.org/animals/{slug}", **summary})

    return dogs


def resolve_post_id(session: requests.Session, url: str) -> Optional[str]:
    """Resolve a profile URL to its WordPress post ID via the rel=shortlink header."""
    try:
        resp = polite_request("HEAD", url, session=session, allow_redirects=True)
        m = re.search(r"[?&]p=(\d+)>;\s*rel=\"?shortlink", resp.headers.get("link", ""))
        if m:
            return m.group(1)
        if resp.status_code >= 400:
            logging.warning(f"HEAD {url} -> HTTP {resp.status_code}")
            return None
        # Some proxies drop Link headers on HEAD — fall back to the page body.
        resp = polite_request("GET", url, session=session)
        m = (re.search(r"rel=['\"]shortlink['\"][^>]*[?&]p=(\d+)", resp.text)
             or re.search(r"\bpostid-(\d+)\b", resp.text))
        return m.group(1) if m else None
    except requests.RequestException as exc:
        logging.warning(f"Could not resolve post id for {url}: {exc}")
        return None


def load_known_ids(client) -> Dict[str, str]:
    """profile URL → animal_id for PawsCo dogs we've already resolved, so routine
    inventory runs only spend requests on newly listed dogs."""
    known: Dict[str, str] = {}
    for table in ("animals", "active_dogs"):
        try:
            res = (client.table(table).select("animal_id, shelter_profile_url")
                   .eq("shelter_id", SHELTER_ID).execute())
            for r in res.data or []:
                if r.get("shelter_profile_url") and r.get("animal_id"):
                    known[r["shelter_profile_url"].rstrip("/")] = r["animal_id"]
        except Exception as exc:
            logging.warning(f"Could not load known {table} ids: {exc}")
    return known


def build_rows(dogs: List[Dict], scraped_at: str, known_ids: Optional[Dict[str, str]] = None) -> List[Dict]:
    session = requests.Session()
    known_ids = known_ids or {}
    rows, seen_ids = [], set()
    for dog in dogs:
        animal_id = known_ids.get(dog["url"].rstrip("/"))
        if not animal_id:
            post_id = resolve_post_id(session, dog["url"])
            if not post_id:
                logging.warning(f"Skipping {dog['url']} — no post id")
                continue
            animal_id = f"{SHELTER_ID}-{post_id}"
        if animal_id in seen_ids:
            continue
        seen_ids.add(animal_id)
        rows.append({
            "animal_id": animal_id,
            "name": dog["name"],
            "gender": dog["gender"],
            "age": dog["age"],
            "weight": dog["weight"],
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": dog["url"],
            "scraped_at": scraped_at,
            "shelter_id": SHELTER_ID,
        })
    return rows


def scrape_inventory() -> List[Dict]:
    """Scrape the adopt page, then full-replace this shelter's active_dogs rows."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_pawsco_inventory")
    logging.info("Starting PAWSCO inventory scrape...")

    try:
        resp = polite_request("GET", LISTING_URL)
        resp.raise_for_status()

        dogs = parse_listing_page(resp.text)
        logging.info(f"Parsed {len(dogs)} dog tiles")
        rows = build_rows(dogs, now_iso(), load_known_ids(client))
        logging.info(f"Resolved {len(rows)} dogs with post ids")

        if len(rows) < MIN_EXPECTED_DOGS or len(rows) < len(dogs) * 0.5:
            # 0 dogs (markup change / block) or most post-id lookups failing —
            # keep the previous inventory rather than wiping it.
            raise RuntimeError(
                f"Parsed {len(dogs)} dog tiles / resolved {len(rows)} ids from {LISTING_URL} "
                f"(HTTP {resp.status_code}, {len(resp.text)} bytes) — page structure may have changed"
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
