"""
DPA (Dallas Pets Alive) — Inventory Scraper

Scrapes the adoptable dogs listing page at dallaspetsalive.org.
The listing uses WP Grid Builder (wpgb) which renders all dog cards
as static HTML in the initial page load — no Playwright needed.

Each dog card contains:
- WordPress post ID (from wpgb-post-XXXXX class)
- Name (from h3 link text)
- Profile URL (from link href)
- Tags: age category, gender, size (from wpgb-block-term spans)

This job runs via Vercel crons (HTTP only).
"""

import json
import logging
import re
import sys
from html import unescape
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "DPA"
SHELTER_NAME = "Dallas Pets Alive"
CITY = "Dallas"
STATE = "TX"

LISTING_URL = "https://dallaspetsalive.org/adopt/adoptable-dogs/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def normalize_gender(tag_text: str) -> Optional[str]:
    """Normalize gender from tag text."""
    lower = tag_text.strip().lower()
    if lower == "female":
        return "Female"
    if lower == "male":
        return "Male"
    return None


def parse_listing_page(html_content: str, scraped_at: str) -> List[Dict]:
    """Parse dog cards from the listing page HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    articles = soup.find_all("article", class_=re.compile(r"wpgb-post-\d+"))
    logging.info(f"Found {len(articles)} articles in listing page")
    
    rows = []
    seen_ids = set()
    
    for article in articles:
        # Extract WordPress post ID
        classes = article.get("class", [])
        wp_id = None
        for cls in classes:
            match = re.match(r"wpgb-post-(\d+)", cls)
            if match:
                wp_id = match.group(1)
                break
        
        if not wp_id or wp_id in seen_ids:
            continue
        seen_ids.add(wp_id)
        
        animal_id = f"DPA-{wp_id}"
        
        # Extract name and profile URL from the h3 link
        name_link = article.find("h3")
        if not name_link:
            continue
        
        link_tag = name_link.find("a")
        if not link_tag:
            continue
        
        name = link_tag.get_text(strip=True)
        profile_url = link_tag.get("href", "")
        
        # Extract tags (age, gender, size)
        tags = article.find_all("span", class_="wpgb-block-term")
        gender = None
        age = None
        
        for tag in tags:
            tag_text = tag.get_text(strip=True)
            g = normalize_gender(tag_text)
            if g:
                gender = g
            elif tag_text.lower() in ("adult", "senior", "puppy", "young"):
                age = tag_text
        
        rows.append({
            "animal_id": animal_id,
            "name": name,
            "gender": gender,
            "age": age,
            "weight": "",
            "city": CITY,
            "state": STATE,
            "shelter_name": SHELTER_NAME,
            "shelter_profile_url": profile_url,
            "scraped_at": scraped_at,
            "shelter_id": SHELTER_ID,
        })
    
    return rows


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_dpa_inventory")
    
    logging.info("Starting DPA inventory scrape...")
    
    try:
        resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        scraped_at = now_iso()
        all_rows = parse_listing_page(resp.text, scraped_at)
        
        logging.info(f"Parsed {len(all_rows)} dogs")
        
        if all_rows:
            logging.info(f"Clearing existing active_dogs for {SHELTER_ID}...")
            client.table("active_dogs").delete().eq("shelter_id", SHELTER_ID).execute()
            
            logging.info(f"Inserting {len(all_rows)} dogs into active_dogs...")
            for chunk_start in range(0, len(all_rows), 100):
                chunk = all_rows[chunk_start:chunk_start + 100]
                client.table("active_dogs").insert(chunk).execute()
            logging.info("Insert complete.")
        
        notes = {"scraped_count": len(all_rows)}
        record_run_finish(client, run_id, "success", notes=json.dumps(notes))
        logging.info("Done.")
        
    except Exception as exc:
        logging.error(f"Inventory scrape failed: {exc}")
        record_run_finish(client, run_id, "error", notes=str(exc))
        raise


if __name__ == "__main__":
    scrape_inventory()
