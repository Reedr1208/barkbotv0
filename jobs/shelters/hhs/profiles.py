import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from jobs.lib.db import now_iso
from jobs.lib.store import BarkbotStore, get_settings, DEFAULT_DOGS_PER_RUN as DOGS_PER_RUN


MAX_EXECUTION_TIME_SECONDS = 240  # 4 minutes

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def extract_bio_with_playwright(page, url: str) -> Tuple[str, Optional[str]]:
    logging.info(f"Navigating to {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass

        # Try to find common text containers, otherwise fallback to body
        bio_text = page.evaluate('''() => {
            let el = document.querySelector('.animal-details, .profile-info, .description');
            if (el) return el.innerText;
            return document.body.innerText;
        }''')
        
        # Try to find og:image
        image_url = page.evaluate('''() => {
            let meta = document.querySelector('meta[property="og:image"]');
            return meta ? meta.content : null;
        }''')
        
        return (bio_text.strip() if bio_text else ""), image_url
    except Exception as e:
        logging.error(f"Playwright failed to fetch {url}: {e}")
        return "", None


def main() -> int:
    args = parse_args()
    settings = get_settings()
    store = BarkbotStore(settings, headers=HEADERS)

    def hhs_fallback_url(animal_id: str) -> str:
        numeric_id = animal_id.replace('HHS-', '')
        return f"https://new.shelterluv.com/embed/animal/HHTX-A-{numeric_id}"
    
    targets = store.get_least_recently_updated_urls(
        shelter_id="HHS",
        limit=DOGS_PER_RUN,
        fallback_url_fn=hhs_fallback_url,
        extra_fields=["age"],
    )
    
    if not targets:
        print("No adoptable dogs found to scrape.")
        return 0
    
    print(f"Scraping the following {len(targets)} URLs:")
    for t in targets:
        print(f" - {t['url']}")

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run(args.triggered_by, len(targets))
    start_time = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            for target in targets:
                # 4-Minute timeout check
                if time.time() - start_time > MAX_EXECUTION_TIME_SECONDS:
                    print("Execution time exceeded 4 minutes limit. Stopping early.")
                    break

                url = target["url"]
                if not url:
                    continue

                processed += 1
                try:
                    bio, image_url = extract_bio_with_playwright(page, url)
                    record = {
                        "shelter_profile_url": url,
                        "animal_id": target["animal_id"],
                        "shelter_name": "Houston Humane Society",
                        "name": target["name"],
                        "gender": target["gender"],
                        "age": target["age"],
                        "weight": None, # Weight is difficult to parse reliably here, pipeline can extract from bio
                        "more_info": "",
                        "bio": bio,
                        "shelter_image_url": image_url,
                        "image_file": None,
                        "image_public_url": None,
                        "city": "Houston",
                        "state": "TX",
                        "shelter_id": "HHS"
                    }
                    
                    try:
                        image_file, image_public_url = store.upload_image(record["animal_id"], record.get("shelter_image_url"))
                        if image_file and image_public_url:
                            record["image_file"] = image_file
                            record["image_public_url"] = image_public_url
                    except Exception as img_exc:
                        print(f"Failed to upload image for {record['animal_id']}: {img_exc}", file=sys.stderr)
                        
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
                    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
                
                time.sleep(settings.scrape_sleep_seconds)

            final_status = "success" if errors == 0 else "partial_success"
            store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
            
            browser.close()
            return 0
        except Exception as exc:
            store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
            browser.close()
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    raise SystemExit(main())
