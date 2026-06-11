#!/usr/bin/env python3
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from supabase import create_client

BASE_URL = "https://www.pawschicago.org"
START_URL = "https://www.pawschicago.org/our-work/pets-adoption/pets-available"

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.75
MAX_LOAD_MORE_PAGES = 50

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

DOG_HREF_RE = re.compile(r"/pet-available-for-adoption/showdog/(\d+)(?:[/?#].*)?$", re.I)
DOG_COUNT_RE = re.compile(r"Dogs:\s*Available\s*for\s*Adoption\s*\((\d+)\)", re.I)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_supabase_client():
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc

def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()

def absolute_url(value: str | None, base_url: str = BASE_URL) -> str:
    return html.unescape(urljoin(base_url, value or "")).strip()

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": START_URL,
        }
    )
    return session

def fetch(session: requests.Session, url: str) -> str:
    print(f"Fetching: {url}")
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.text

def expected_dog_count(soup: BeautifulSoup) -> int | None:
    candidates: list[str] = []
    dog_header = soup.select_one("article.dogs h1")
    if dog_header:
        candidates.append(dog_header.get_text(" ", strip=True))
    candidates.append(soup.get_text(" ", strip=True))

    for text in candidates:
        match = DOG_COUNT_RE.search(clean_text(text))
        if match:
            return int(match.group(1))
    return None

def find_card_for_link(a: Tag) -> Tag:
    return a.find_parent(class_="adopt-pet") or a.find_parent("li") or a.find_parent("div") or a

def name_from_card(card: Tag) -> str:
    h3 = card.find("h3")
    if h3:
        return clean_text(h3.get_text(" ", strip=True))
    img = card.find("img")
    if img and img.get("alt"):
        return clean_text(img.get("alt"))
    text = clean_text(card.get_text(" ", strip=True))
    return text[:120]

def parse_dogs(soup: BeautifulSoup, base_url: str = BASE_URL) -> list[dict]:
    records: list[dict] = []
    seen_ids: set[str] = set()

    scopes: list[Tag | BeautifulSoup] = list(soup.select("article.dogs")) or [soup]

    for scope in scopes:
        for a in scope.select('a[href*="/pet-available-for-adoption/showdog/"]'):
            href = html.unescape(a.get("href", ""))
            match = DOG_HREF_RE.search(href)
            if not match:
                continue

            native_id = match.group(1)
            animal_id = f"PAWSCH-{native_id}"
            
            if animal_id in seen_ids:
                continue
            seen_ids.add(animal_id)

            card = find_card_for_link(a)
            name = name_from_card(card)
            if not name:
                continue

            records.append({
                "animal_id": animal_id,
                "name": name.replace("*", "").strip().title(),
                "gender": "",
                "age": "",
                "weight": "",
                "city": "Chicago",
                "state": "IL",
                "shelter_name": "PAWS Chicago",
                "shelter_id": "PAWSCH",
                "scraped_at": now_iso()
            })

    return records

def find_dog_load_more_url(soup: BeautifulSoup, base_url: str = BASE_URL) -> str:
    selectors = [
        "#dogs-load-more-button[data-url]",
        "a.lazyload-button#dogs-load-more-button[data-url]",
        '[id*="dogs-load-more"][data-url]',
        '.lazyload-button[data-url][id*="dogs"]',
    ]
    for selector in selectors:
        button = soup.select_one(selector)
        if button and button.get("data-url"):
            return absolute_url(button.get("data-url"), base_url)
    return ""

def extract_html_fragments(value: any) -> list[str]:
    fragments: list[str] = []
    if isinstance(value, str):
        if "<" in value and ">" in value:
            fragments.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            fragments.extend(extract_html_fragments(child))
    elif isinstance(value, list):
        for child in value:
            fragments.extend(extract_html_fragments(child))
    return fragments

def soup_from_response_text(text: str) -> BeautifulSoup:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
            fragments = extract_html_fragments(payload)
            if fragments:
                return BeautifulSoup("\n".join(fragments), "html.parser")
        except json.JSONDecodeError:
            pass
    return BeautifulSoup(text, "html.parser")

def scrape_all_dogs() -> list[dict]:
    session = make_session()
    
    try:
        initial_html = fetch(session, START_URL)
    except requests.RequestException as exc:
        print(f"Failed to fetch initial page: {exc}")
        return []
        
    soup = BeautifulSoup(initial_html, "html.parser")
    target_count = expected_dog_count(soup)
    records = parse_dogs(soup)
    
    print(f"Initial parse: found {len(records)} dogs. Target: {target_count}")

    next_url = find_dog_load_more_url(soup)
    seen_urls: set[str] = set()

    for page_num in range(1, MAX_LOAD_MORE_PAGES + 1):
        if not next_url:
            break
        if next_url in seen_urls:
            break
        if target_count is not None and len(records) >= target_count:
            break
            
        seen_urls.add(next_url)
        time.sleep(REQUEST_DELAY_SECONDS)

        try:
            more_text = fetch(session, next_url)
        except requests.RequestException as exc:
            print(f"Load more failed: {exc}")
            break

        more_soup = soup_from_response_text(more_text)
        parsed = parse_dogs(more_soup)
        
        added = 0
        existing_ids = {r["animal_id"] for r in records}
        for r in parsed:
            if r["animal_id"] not in existing_ids:
                records.append(r)
                existing_ids.add(r["animal_id"])
                added += 1

        new_next_url = find_dog_load_more_url(more_soup)
        print(f"Load More {page_num}: parsed {len(parsed)}, added {added}, total {len(records)}")

        if added == 0 and (not new_next_url or new_next_url == next_url):
            break
        next_url = new_next_url

    return records

def save_to_supabase(dogs: list[dict]):
    if not dogs:
        print("No dogs to save.")
        return

    if len(dogs) < 10:
        raise RuntimeError(f"Safety check failed: Only {len(dogs)} dogs scraped. Aborting.")

    client = get_supabase_client()
    print("Clearing existing active_dogs table data for PAWSCH...")
    client.table("active_dogs").delete().eq("shelter_id", "PAWSCH").execute()

    print(f"Inserting {len(dogs)} dogs into active_dogs...")
    client.table("active_dogs").insert(dogs).execute()

def main():
    dogs = scrape_all_dogs()
    save_to_supabase(dogs)
    print(f"Done. Wrote {len(dogs)} dogs to active_dogs table in Supabase.")

if __name__ == "__main__":
    main()
