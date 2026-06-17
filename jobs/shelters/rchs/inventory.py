"""
RCHS (Rancho Coastal Humane Society) — Inventory Scraper

Uses the WordPress REST API to fetch adoptable dog listings.
Each dog is a blog post in the "Dogs" category (category ID 38).
No Playwright needed — pure HTTP requests.

This job runs via Vercel crons.
"""

import json
import logging
import re
import sys
import time
from typing import Dict, List, Optional
from html import unescape

import requests

from jobs.lib.db import now_iso, get_supabase_client, record_run_start, record_run_finish


SHELTER_ID = "RCHS"
SHELTER_NAME = "Rancho Coastal Humane Society"
CITY = "San Diego"
STATE = "CA"

# WordPress REST API endpoint — category 38 = "Dogs"
WP_API_URL = "https://rchumanesociety.org/wp-json/wp/v2/posts"
WP_CATEGORY_ID = 38

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def clean_text(value: Optional[str]) -> Optional[str]:
    """Strip HTML tags, shortcodes, and normalize whitespace."""
    if not value:
        return None
    # Remove WPBakery shortcodes like [vc_row], [vc_column], etc.
    value = re.sub(r'\[/?[^\]]+\]', '', value)
    # Remove HTML tags
    value = re.sub(r'<[^>]+>', ' ', value)
    # Decode HTML entities
    value = unescape(value)
    # Normalize whitespace
    value = re.sub(r'\s+', ' ', value).strip()
    return value or None


def extract_dog_info(content_text: str) -> Dict[str, Optional[str]]:
    """Extract breed, sex, age, weight from the rendered content text.
    
    The typical format is:
    'Terrier mix – Brown Brindle & White Female 3 years 66 pounds Meet ...'
    
    Fields appear as bullet points in the HTML:
    • Breed — Color
    • Sex
    • Age
    • Weight
    """
    info = {"breed": None, "gender": None, "age": None, "weight": None}
    
    if not content_text:
        return info

    # The content starts with breed info before the bio text
    # Split at "Meet " or "Click here" to separate info from bio
    header = re.split(r'(?:Meet |Click here )', content_text, maxsplit=1)[0]
    
    # Try to extract structured info
    # Pattern: "Breed – Color Gender Age Weight"
    # e.g. "Terrier mix – Brown Brindle & White Female 3 years 66 pounds"
    
    # Gender
    gender_match = re.search(r'\b(Male|Female)\b', header, re.I)
    if gender_match:
        info["gender"] = gender_match.group(1).title()
    
    # Age — e.g. "3 years", "2 ½ years", "8 months", "1 year"
    age_match = re.search(r'(\d+\s*(?:½\s*)?(?:year|month|week)s?)', header, re.I)
    if age_match:
        info["age"] = age_match.group(1).strip()
    
    # Weight — e.g. "66 pounds", "12 ½ pounds"
    weight_match = re.search(r'(\d+\s*(?:½\s*)?(?:pound|lb)s?)', header, re.I)
    if weight_match:
        info["weight"] = weight_match.group(1).strip()
    
    # Breed — everything before the gender
    if gender_match:
        breed_text = header[:gender_match.start()].strip()
        # Clean up trailing dashes/spaces
        breed_text = re.sub(r'[\s–-]+$', '', breed_text).strip()
        if breed_text and len(breed_text) > 2:
            info["breed"] = breed_text

    return info


def fetch_inventory() -> List[Dict]:
    """Fetch all dogs from the WordPress REST API."""
    all_posts = []
    page = 1
    per_page = 100  # Max allowed by WP
    
    while True:
        params = {
            "categories": WP_CATEGORY_ID,
            "per_page": per_page,
            "page": page,
            "_fields": "id,title,link,content,slug,date",
        }
        
        logging.info(f"Fetching WP API page {page}...")
        resp = requests.get(WP_API_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        posts = resp.json()
        if not posts:
            break
        
        all_posts.extend(posts)
        
        # Check if there are more pages
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1
    
    return all_posts


def scrape_inventory() -> None:
    """Main inventory scraper function."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_rchs_inventory")
    
    logging.info("Starting RCHS inventory scrape...")
    
    try:
        posts = fetch_inventory()
        logging.info(f"Fetched {len(posts)} posts from WP API")
        
        scraped_at = now_iso()
        all_rows = []
        
        for post in posts:
            title = unescape(post["title"]["rendered"])
            content_raw = post["content"]["rendered"]
            content_text = clean_text(content_raw)
            
            wp_post_id = post["id"]
            animal_id = f"RCHS-{wp_post_id}"
            profile_url = post["link"]
            
            # Extract structured info from content
            info = extract_dog_info(content_text or "")
            
            row = {
                "animal_id": animal_id,
                "name": title,
                "gender": info["gender"],
                "age": info["age"],
                "weight": info["weight"],
                "city": CITY,
                "state": STATE,
                "shelter_name": SHELTER_NAME,
                "shelter_profile_url": profile_url,
                "scraped_at": scraped_at,
                "shelter_id": SHELTER_ID,
            }
            
            all_rows.append(row)
            logging.info(f"Added dog: {title} | {animal_id}")
        
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
