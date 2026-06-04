import os
import re
import sys
import time
import json
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin
from typing import Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    pass

from supabase import create_client

BASE_URL = "https://www.adoptapet.com/shelter/76010-humane-society-of-southern-arizona-tucson-arizona"
SHELTER_ID = "HUMANESOCIETYSOAZ"
DB_SHELTER_ID = "HSSA"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

CARD_SELECTOR = 'section[data-testid="pets-at-awo"] a[data-testid="pet-card-link"][href*="/pet/"]'
FALLBACK_CARD_SELECTOR = 'a[data-testid="pet-card-link"][href*="/pet/"]'

MAX_EXECUTION_TIME_SECONDS = 200  # Leave 40 seconds buffer for Vercel 4m timeout

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_supabase_client():
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
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


def build_page_url(page_num: int) -> str:
    if page_num <= 1:
        return f"{BASE_URL}#available-pets"
    return f"{BASE_URL}?{urlencode({'internalPage': page_num})}#available-pets"


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+,", ",", value)
    value = re.sub(r",\s*", ", ", value)
    return value or None


def normalize_gender(value: Optional[str]) -> Optional[str]:
    value = clean_text(value)
    if not value:
        return None
    lowered = value.lower()
    if lowered in {"f", "female"}:
        return "Female"
    if lowered in {"m", "male"}:
        return "Male"
    return value


def get_pet_numeric_id(href: str) -> Optional[str]:
    match = re.search(r"/pet/(\d+)(?:-|$)", href or "")
    return match.group(1) if match else None


def best_image_url(img_tag) -> Optional[str]:
    if not img_tag:
        return None
    for attr in ("src", "data-src"):
        value = img_tag.get(attr)
        if value:
            return value
    srcset = img_tag.get("srcset") or img_tag.get("data-srcset")
    if srcset:
        candidates = [part.strip().split(" ")[0] for part in srcset.split(",") if part.strip()]
        if candidates:
            return candidates[-1]
    return None


def parse_gender_age(text: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    text = clean_text(text)
    if not text:
        return None, None

    match = re.match(r"^(Male|Female|M|F)\s*,\s*(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return normalize_gender(text), None

    gender = normalize_gender(match.group(1))
    age = clean_text(match.group(2))
    return gender, age


def parse_cards_from_html(html: str, scraped_at: str) -> List[Dict[str, Optional[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.select_one('section[data-testid="pets-at-awo"]')
    if scope:
        cards = scope.select('a[data-testid="pet-card-link"][href*="/pet/"]')
    else:
        cards = soup.select(FALLBACK_CARD_SELECTOR)

    rows = []
    for card in cards:
        href = urljoin(BASE_URL, card.get("href") or "")
        numeric_id = get_pet_numeric_id(href)
        if not numeric_id:
            continue

        name_el = card.select_one(".name")
        name = clean_text(name_el.get_text(" ", strip=True) if name_el else None)

        info_box = card.select_one(".sex")
        info_lines = []
        if info_box:
            info_lines = [clean_text(p.get_text(" ", strip=True)) for p in info_box.select("p")]
            info_lines = [line for line in info_lines if line]

        gender, age = parse_gender_age(info_lines[0] if len(info_lines) >= 1 else None)
        
        # We store weight as empty string in active_dogs if unknown
        weight = ""

        img = card.select_one("img.pet-image, img[alt^='Photo of'], img")
        image_url = best_image_url(img)

        rows.append(
            {
                "animal_id": f"hssa-{numeric_id}",
                "name": name,
                "gender": gender,
                "age": age,
                "weight": weight,
                "scraped_at": scraped_at,
                "shelter_id": DB_SHELTER_ID,
            }
        )
    return rows


def wait_for_hydrated_page(page, page_num: int, timeout_seconds: float = 18.0) -> None:
    if page_num <= 1:
        return
    expected_start = (page_num - 1) * 12 + 1
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            body_text = page.locator("body").inner_text(timeout=1000)
            normalized = re.sub(r"\s+", " ", body_text)
            if re.search(rf"Showing\s+{expected_start}\s*[-–]\s*\d+\s+of", normalized):
                return
        except Exception:
            pass
        time.sleep(0.5)


def get_next_page(client) -> int:
    try:
        res = client.table("scrape_runs").select("notes").eq("triggered_by", "cron_hssa_inventory").order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get("notes"):
            notes = json.loads(res.data[0]["notes"])
            return notes.get("next_page", 1)
    except Exception as e:
        print(f"Error reading next_page from scrape_runs: {e}")
    return 1


def record_run_start(client, triggered_by: str) -> int:
    payload = {
        "triggered_by": triggered_by,
        "source_count": 0,
        "started_at": now_iso(),
        "status": "running",
    }
    row = client.table("scrape_runs").insert(payload).execute().data[0]
    return row["id"]


def record_run_finish(client, run_id: int, status: str, notes_dict: dict) -> None:
    payload = {
        "status": status,
        "notes": json.dumps(notes_dict),
        "finished_at": now_iso(),
    }
    client.table("scrape_runs").update(payload).eq("id", run_id).execute()


def scrape_inventory() -> None:
    start_time = time.time()
    client = get_supabase_client()
    
    run_id = record_run_start(client, "cron_hssa_inventory")
    start_page = get_next_page(client)
    print(f"Resuming HSSA inventory scrape from page {start_page}...")

    # Dynamic install of Playwright Firefox if running in Vercel environment
    import os
    if "VERCEL" in os.environ or "storage_SUPABASE_URL" in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/ms-playwright"
        os.system("python -m playwright install firefox")

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    scraped_at = now_iso()
    all_rows = []
    seen_animal_ids = set()
    current_page = start_page
    status = "success"

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1200},
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        while True:
            # Time check
            if time.time() - start_time > MAX_EXECUTION_TIME_SECONDS:
                print("Approaching max execution time. Pausing scrape.")
                status = "partial_success"
                break

            url = build_page_url(current_page)
            print(f"Fetching page {current_page}: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(CARD_SELECTOR, timeout=15000)
            except PlaywrightTimeoutError:
                print("No pet cards found or timeout; stopping.")
                current_page = 1  # Reset to beginning for next run
                break

            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            
            wait_for_hydrated_page(page, current_page)

            for _ in range(3):
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(250)
            page.mouse.wheel(0, -3600)
            page.wait_for_timeout(500)

            rendered_html = page.content()
            rows = parse_cards_from_html(rendered_html, scraped_at)
            
            new_rows_on_page = 0
            for row in rows:
                animal_id = row["animal_id"]
                if not animal_id or animal_id in seen_animal_ids:
                    continue
                seen_animal_ids.add(animal_id)
                all_rows.append(row)
                new_rows_on_page += 1

            if new_rows_on_page == 0:
                print("Page had no new animal IDs; stopping and resetting to page 1.")
                current_page = 1
                break

            current_page += 1
            time.sleep(1)

        context.close()
        browser.close()

    print(f"Scraped {len(all_rows)} dogs.")

    if all_rows:
        # Upsert into active_dogs (no delete because this might just be a subset)
        for chunk_start in range(0, len(all_rows), 100):
            chunk = all_rows[chunk_start:chunk_start + 100]
            client.table("active_dogs").upsert(chunk, on_conflict="animal_id").execute()
            
    notes = {"next_page": current_page, "scraped_count": len(all_rows)}
    record_run_finish(client, run_id, status, notes)
    print("Done.")

if __name__ == "__main__":
    scrape_inventory()
