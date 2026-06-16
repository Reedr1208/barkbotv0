#!/usr/import/env python3
"""
Scrape AHS Newark adoptable DOG inventory from ahscares.org/newark-adoptables/.
"""

import os
import re
import html
import time
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Iterable, List
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from jobs.lib.db import get_supabase_client

# =============================================================================
# User-editable variables
# =============================================================================

START_URL = "https://ahscares.org/newark-adoptables/"
DOG_CLAN_NAME = "dog"
MAX_WIDGET_PAGES = 75
REQUEST_TIMEOUT_SECONDS = 30
SLEEP_BETWEEN_REQUESTS_SECONDS = 0.35

SHELTER_ID = "AHSCN"
CITY = "Newark"
STATE = "NJ"
SHELTER_NAME = "Associated Humane Societies - Newark"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": START_URL,
}

# =============================================================================
# Data model
# =============================================================================

@dataclass
class DogRecord:
    name: str
    animal_id: str
    shelter_profile_url: str
    public_image_url: str
    source_widget_url: str = ""

# =============================================================================
# Helpers
# =============================================================================




def make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=4, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def fetch_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text

def normalize_space(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def absolute_url(base_url: str, maybe_url: str | None) -> str:
    if not maybe_url:
        return ""
    maybe_url = html.unescape(maybe_url).strip()
    if maybe_url.startswith("//"):
        return "https:" + maybe_url
    return urljoin(base_url, maybe_url)

def set_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(html.unescape(url))
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))

def get_query_first(url: str, key: str) -> str:
    parsed = urlparse(html.unescape(url))
    query = parse_qs(parsed.query, keep_blank_values=True)
    values = query.get(key) or []
    return values[0] if values else ""

def extract_pet_id(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    match = re.search(r"/(?:pet)/(\d+)(?:\b|/|$)", parsed.path)
    return match.group(1) if match else ""

def is_adoptapet_profile_url(url: str) -> bool:
    parsed = urlparse(html.unescape(url))
    return "adoptapet.com" in parsed.netloc.lower() and bool(extract_pet_id(url))

def extract_shelter_id_from_url(url: str) -> str:
    for key in ("shelter_id", "awos[0]", "awos%5B0%5D"):
        value = get_query_first(url, key)
        if value: return value
    match = re.search(r"awos(?:%5B|\[)0(?:%5D|\])=(\d+)", url)
    if match: return match.group(1)
    match = re.search(r"shelter_id=(\d+)", url)
    if match: return match.group(1)
    return ""

def build_searchtools_url(shelter_id: str, clan_name: str = DOG_CLAN_NAME) -> str:
    params = {
        "shelter_id": shelter_id, "title": "", "color": "green", "clan_name": clan_name,
        "size": "450x320_list", "sort_by": "pet_name", "hide_clan_filter_p": "",
    }
    return "https://searchtools.adoptapet.com/cgi-bin/searchtools.cgi/portable_pet_list?" + urlencode(params)

def discover_widget_urls(start_html: str) -> list[str]:
    soup = BeautifulSoup(start_html, "html.parser")
    candidates = []
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src")
        if src and ("searchtools.adoptapet.com" in src.lower() or "adoptapet.com/pet-search" in src.lower()):
            candidates.append(absolute_url(START_URL, src))
            
    expanded = []
    for url in candidates:
        if "searchtools.adoptapet.com" in url.lower():
            expanded.append(set_query_param(url, "clan_name", DOG_CLAN_NAME))
            expanded.append(url)
        shelter_id = extract_shelter_id_from_url(url)
        if shelter_id:
            expanded.append(build_searchtools_url(shelter_id, DOG_CLAN_NAME))

    seen = set()
    out = []
    for url in expanded:
        url = html.unescape(url).strip()
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out

def is_usable_image_url(url: str) -> bool:
    if not url: return False
    lowered = url.lower()
    if lowered.startswith("data:") or any(bad in lowered for bad in ("/spinner", "loading", "blank.gif", "placeholder")):
        return False
    return any(ext in lowered for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"))

def image_url_from_img(base_url: str, img: Tag) -> str:
    for attr in ("data-src", "data-lazy-src", "data-original", "data-echo", "src"):
        value = img.get(attr)
        if value:
            url = absolute_url(base_url, value)
            if is_usable_image_url(url): return url
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        candidates = []
        for part in srcset.split(","):
            bits = part.strip().split()
            if not bits: continue
            url = absolute_url(base_url, bits[0])
            width = int(bits[1][:-1]) if len(bits) > 1 and bits[1].endswith("w") else 0
            if is_usable_image_url(url): candidates.append((width, url))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    return ""

def pick_image_url(base_url: str, container: Tag) -> str:
    for img in container.find_all("img"):
        url = image_url_from_img(base_url, img)
        if url: return url
    return ""

def extract_pet_id_from_url_strict(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    match = re.search(r"/(?:pet)/(\d+)(?:\b|/|$)", parsed.path)
    return match.group(1) if match else ""

def likely_tile_container(anchor: Tag) -> Tag:
    current = anchor
    best = anchor
    for _ in range(8):
        parent = current.parent
        if not isinstance(parent, Tag): break
        text = normalize_space(parent.get_text(" "))
        has_img = parent.find("img") is not None
        has_link = bool(parent.find("a", href=lambda h: bool(h and extract_pet_id_from_url_strict(h))))
        if has_img and has_link:
            best = parent
            if 20 < len(text) < 700: return parent
        current = parent
    return best

def clean_name(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"\b(Adopt|Meet|View|Details|More Info|Learn More)\b", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\s+", " ", value).strip(" -–—:|,\t\n\r")
    if len(value) > 60 or re.search(r"\b(dog|cat|kitten|puppy|breed|shelter)\b", value, re.I): return ""
    return value

def parse_name_from_phrase(value: str) -> str:
    value = normalize_space(value)
    if not value: return ""
    patterns = [r"\bAdopt\s+(.+?)\s+(?:a|an)\s+", r"\bMeet\s+(.+?)(?:\s*$|\s+-|\s+\|)", r"^(.+?),\s+(?:a|an)\s+", r"^(.+?)\s+-\s+(?:Adoptable|Dog|Puppy|Male|Female)\b"]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match: return clean_name(match.group(1))
    return clean_name(value)

def is_likely_name(value: str) -> bool:
    if not value: return False
    bad_fragments = ("adopt", "details", "learn more", "dog", "cat", "puppy", "shelter")
    if any(f in value.lower() for f in bad_fragments): return False
    if len(value) > 45 or re.search(r"https?://|\d{4,}", value): return False
    return True

def best_name_for_tile(anchor: Tag, container: Tag) -> str:
    candidates = []
    for selector in (".pet-name", ".name", "h1", "h2", "h3", "h4", "strong", "b"):
        for node in container.select(selector):
            text = normalize_space(node.get_text(" "))
            if text: candidates.append(text)
            
    link_text = normalize_space(anchor.get_text(" "))
    if link_text: candidates.append(link_text)
    
    for node in [anchor, *container.find_all("img")]:
        for attr in ("aria-label", "alt", "title"):
            val = node.get(attr)
            if val: candidates.append(val)
            
    seen = set()
    for raw in candidates:
        raw = normalize_space(raw)
        if not raw or raw.lower() in seen: continue
        seen.add(raw.lower())
        parsed = parse_name_from_phrase(raw)
        if parsed and is_likely_name(parsed): return parsed
    return ""

def text_indicates_cat(text: str) -> bool:
    lowered = f" {text.lower()} "
    cat_terms = (" cat ", " cats ", " kitten ", " feline ", " tabby ")
    dog_terms = (" dog ", " dogs ", " puppy ", " canine ", " terrier", " pit bull")
    has_cat = any(t in lowered for t in cat_terms)
    has_dog = any(t in lowered for t in dog_terms)
    return has_cat and not has_dog

def parse_records_from_widget_html(widget_html: str, widget_url: str) -> list[DogRecord]:
    soup = BeautifulSoup(widget_html, "html.parser")
    records = []
    seen_ids = set()

    for anchor in soup.find_all("a", href=True):
        profile_url = absolute_url(widget_url, anchor.get("href"))
        if not is_adoptapet_profile_url(profile_url): continue
        pet_id = extract_pet_id_from_url_strict(profile_url)
        if not pet_id or pet_id in seen_ids: continue

        container = likely_tile_container(anchor)
        container_text = normalize_space(container.get_text(" "))

        clan_name = get_query_first(widget_url, "clan_name").lower()
        if clan_name != DOG_CLAN_NAME and text_indicates_cat(container_text + " " + profile_url):
            continue

        name = best_name_for_tile(anchor, container)
        image_url = pick_image_url(widget_url, container)

        records.append(DogRecord(name=name, animal_id=f"{SHELTER_ID}-{pet_id}", shelter_profile_url=profile_url, public_image_url=image_url, source_widget_url=widget_url))
        seen_ids.add(pet_id)

    return records

def discover_widget_page_links(widget_html: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(widget_html, "html.parser")
    links = []
    for anchor in soup.find_all("a", href=True):
        href = absolute_url(current_url, anchor.get("href"))
        if not href or is_adoptapet_profile_url(href): continue
        parsed = urlparse(href)
        current_parsed = urlparse(current_url)
        if parsed.netloc.lower() == current_parsed.netloc.lower():
            text_l = normalize_space(anchor.get_text(" ")).lower()
            query_keys = set(parse_qs(parsed.query).keys())
            if "portable_pet_list" in href.lower() or any(t in text_l for t in ("next", "more", "›", "»")) or bool(query_keys & {"page", "paged", "start"}):
                links.append(href)
                
    for match in re.finditer(r"https?://[^\"'<>\s]+(?:portable_pet_list|searchtools\.cgi)[^\"'<>\s]*", widget_html):
        links.append(html.unescape(match.group(0)))

    out = []
    seen = set()
    for link in links:
        link = html.unescape(link).strip()
        if link and link != current_url and link not in seen:
            seen.add(link)
            out.append(link)
    return out

def crawl_widget(session: requests.Session, start_widget_url: str) -> list[DogRecord]:
    records_by_id = {}
    queue = [start_widget_url]
    visited = set()
    page_num = 0

    while queue and page_num < MAX_WIDGET_PAGES:
        widget_url = queue.pop(0)
        if widget_url in visited: continue
        visited.add(widget_url)
        page_num += 1

        logging.info(f"Fetching widget page {page_num}: {widget_url}")
        widget_html = fetch_text(session, widget_url)

        page_records = parse_records_from_widget_html(widget_html, widget_url)
        for record in page_records:
            if record.animal_id not in records_by_id:
                records_by_id[record.animal_id] = record

        for link in discover_widget_page_links(widget_html, widget_url):
            if link not in visited and link not in queue:
                queue.append(link)

        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    return list(records_by_id.values())

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    
    session = make_session()
    start_html = fetch_text(session, START_URL)
    widget_urls = discover_widget_urls(start_html)

    if not widget_urls:
        raise RuntimeError("Could not find an Adopt-a-Pet widget on START_URL.")

    all_records = []
    for widget_url in widget_urls:
        try:
            records = crawl_widget(session, widget_url)
            if records:
                all_records = records
                break
        except Exception as exc:
            logging.exception(f"Widget crawl failed for {widget_url}: {exc}")

    if not all_records:
        logging.warning("No records found across any widgets.")
        return

    # De-dupe
    final_by_id = {}
    for record in all_records:
        if record.animal_id not in final_by_id:
            final_by_id[record.animal_id] = record

    final_records = list(final_by_id.values())
    logging.info(f"Scraped {len(final_records)} records.")

    if len(final_records) < 5:
        logging.warning(f"Only {len(final_records)} records found. Aborting full replacement to prevent data loss.")
        return

    db_records = []
    for rec in final_records:
        db_records.append({
            "animal_id": rec.animal_id,
            "name": rec.name,
            "shelter_profile_url": rec.shelter_profile_url,
            "public_image_url": rec.public_image_url,
            "shelter_id": SHELTER_ID,
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        })

    if not dry_run:
        client = get_supabase_client()
        logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
        client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()
        
        logging.info(f"Inserting {len(db_records)} records into active_dogs...")
        client.table("active_dogs").insert(db_records).execute()
        logging.info("Insert complete.")
    else:
        logging.info(f"[DRY RUN] Would delete active_dogs for {SHELTER_ID} and insert {len(db_records)} records.")

if __name__ == "__main__":
    main()
