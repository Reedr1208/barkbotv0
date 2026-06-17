"""
SAPA (San Antonio Pets Alive) — Profile Scraper

Scrapes detailed profiles from Shelterluv embed pages using Playwright.
SAPA uses the newer Shelterluv version (Livewire-based) which does not
embed structured JSON data in the HTML, so Playwright is required.

This job must run via GitHub Actions (not Vercel crons).

Adapted from the HHS profiles scraper which uses the same approach.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from jobs.lib.db import now_iso
from jobs.lib.store import BarkbotStore, get_settings, DEFAULT_DOGS_PER_RUN as DOGS_PER_RUN


MAX_EXECUTION_TIME_SECONDS = 240  # 4 minutes

SHELTER_ID = "SAPA"
SHELTERLUV_PREFIX = "SAPA"
SHELTER_NAME = "San Antonio Pets Alive"
CITY = "San Antonio"
STATE = "TX"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

# JavaScript to extract profile data from the rendered Shelterluv page
EXTRACT_PROFILE_JS = '''() => {
    const result = {bio: '', image_url: null, name: '', breed: '', age: '', gender: '', weight: '', species: ''};
    
    // Extract species from the :animal JSON attribute (available in server-side HTML)
    const animalEl = document.querySelector('[\\:animal]');
    if (animalEl) {
        try {
            const raw = animalEl.getAttribute(':animal');
            if (raw) {
                let decoded = raw.replace(/&quot;/g, '"').replace(/&amp;/g, '&');
                const parsed = JSON.parse(decoded);
                if (parsed.species) result.species = parsed.species;
            }
        } catch(e) {}
    }
    
    // Try og:image first for best quality photo
    const ogImage = document.querySelector('meta[property="og:image"]');
    if (ogImage && ogImage.content) {
        result.image_url = ogImage.content;
    }
    
    // If no og:image, look for the main animal photo in the rendered page
    if (!result.image_url) {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            const src = img.currentSrc || img.src || '';
            if (src && (src.includes('shelterluv') || src.includes('s3.')) && 
                !src.includes('logo') && !src.includes('favicon') && !src.includes('error_404')) {
                result.image_url = src;
                break;
            }
        }
    }
    
    // Get the full page text for bio extraction
    const bodyText = document.body.innerText || '';
    
    // Extract name: look for the animal name heading
    // Shelterluv typically shows the name prominently before "ANIMAL ID"
    const nameMatch = bodyText.match(/^(?:Item \\d+ of \\d+\\n)?(.+?)\\nANIMAL ID/s);
    if (nameMatch) {
        result.name = nameMatch[1].trim();
    } else {
        // Fallback: try page title, cleaning the Shelterluv suffix
        const title = document.title || '';
        const cleaned = title.replace(/\\s*is available for adoption at.*$/i, '').trim();
        if (cleaned && cleaned.length < 50) {
            result.name = cleaned;
        }
    }
    
    // Build a structured bio from the page content
    const allText = bodyText;
    const sections = [];
    
    // Extract breed from text patterns
    const breedMatch = allText.match(/BREED\\n(.+?)\\n/i);
    if (breedMatch) {
        result.breed = breedMatch[1].trim();
        sections.push("Breed: " + result.breed);
    }
    
    // Extract sex/gender  
    const sexMatch = allText.match(/SEX\\n(.+?)\\n/i);
    if (sexMatch) {
        result.gender = sexMatch[1].trim();
        sections.push("Sex: " + result.gender);
    }
    
    // Extract weight
    const weightMatch = allText.match(/WEIGHT\\n(.+?)\\n/i);
    if (weightMatch) {
        result.weight = weightMatch[1].trim();
        sections.push("Weight: " + result.weight);
    }
    
    // Extract age
    const ageMatch = allText.match(/AGE\\n(.+?)\\n/i);
    if (ageMatch) {
        result.age = ageMatch[1].trim();
        sections.push("Age: " + result.age);
    }
    
    // Extract location
    const locMatch = allText.match(/LOCATION\\n(.+?)\\n/i);
    if (locMatch) sections.push("Location: " + locMatch[1].trim());
    
    // Extract the main description/bio text
    // It typically comes after "Apply for Adoption" or "ATTRIBUTES" section
    const descMatch = allText.match(/(?:Apply for Adoption|ATTRIBUTES[\\s\\S]*?\\n\\n)([\\s\\S]+?)(?:$|\\nAdopt a|\\nShelterluv|\\nPowered by)/i);
    if (descMatch) {
        const desc = descMatch[1].trim();
        if (desc.length > 10) sections.push(desc);
    } else {
        // Fallback: capture everything after the structured fields
        const afterFields = allText.match(/(?:LOCATION\\n.+?\\n|AGE\\n.+?\\n)(?:Apply for Adoption\\n)?([\\s\\S]+?)(?:$|\\nPowered by)/i);
        if (afterFields) {
            const desc = afterFields[1].trim();
            if (desc.length > 10) sections.push(desc);
        }
    }
    
    result.bio = sections.join("\\n\\n");
    
    return result;
}'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def fallback_url(animal_id: str) -> str:
    """Generate Shelterluv profile URL from our animal_id."""
    numeric_id = animal_id.replace(f"{SHELTER_ID}-", "")
    return f"https://new.shelterluv.com/embed/animal/{SHELTERLUV_PREFIX}-A-{numeric_id}"


def extract_bio_with_playwright(page, url: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Navigate to a Shelterluv profile page and extract data using Playwright."""
    logging.info(f"Navigating to {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            pass
        
        # Wait a bit for dynamic content
        page.wait_for_timeout(2000)
        
        # Check for 404 page
        is_404 = page.evaluate('''() => {
            return !!document.querySelector('img[src*="error_404"]') || 
                   document.body.innerText.includes("Page Not Found") ||
                   document.body.innerText.includes("404");
        }''')
        
        if is_404:
            raise ValueError("NOT_FOUND")
        
        # Extract profile data
        profile_data = page.evaluate(EXTRACT_PROFILE_JS)
        
        return profile_data, profile_data.get("image_url")
    except ValueError:
        raise
    except Exception as e:
        logging.error(f"Playwright failed to fetch {url}: {e}")
        return {}, None


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    args = parse_args()
    settings = get_settings()
    store = BarkbotStore(settings, headers=HEADERS)

    targets = store.get_least_recently_updated_urls(
        shelter_id=SHELTER_ID,
        limit=DOGS_PER_RUN,
        fallback_url_fn=fallback_url,
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
                
                # Redirect non-Shelterluv URLs to the Shelterluv embed
                if 'shelterluv.com' not in url:
                    url = fallback_url(target["animal_id"])

                processed += 1
                try:
                    profile_data, image_url = extract_bio_with_playwright(page, url)
                    
                    # Filter out non-dogs (cats, rabbits, etc.)
                    species = (profile_data.get("species") or "").strip().lower()
                    if species and species != "dog":
                        logging.info(f"Skipping {target['animal_id']} — species: {species}")
                        raise ValueError("NOT_A_DOG")
                    
                    bio = profile_data.get("bio", "")
                    
                    record = {
                        "shelter_profile_url": url,
                        "animal_id": target["animal_id"],
                        "shelter_name": SHELTER_NAME,
                        "name": profile_data.get("name") or target.get("name", ""),
                        "gender": profile_data.get("gender") or target.get("gender", ""),
                        "age": profile_data.get("age") or target.get("age", ""),
                        "weight": profile_data.get("weight", ""),
                        "more_info": "",
                        "bio": bio,
                        "shelter_image_url": image_url,
                        "image_file": None,
                        "image_public_url": None,
                        "city": CITY,
                        "state": STATE,
                        "shelter_id": SHELTER_ID,
                    }

                    try:
                        image_file, image_public_url = store.upload_image(
                            record["animal_id"], record.get("shelter_image_url")
                        )
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
                except ValueError as ve:
                    if str(ve) == "NOT_FOUND":
                        # Dog was adopted — remove from active_dogs
                        aid = target.get("animal_id", "")
                        try:
                            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                            print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_404"}))
                        except Exception as del_exc:
                            print(json.dumps({"animal_id": aid, "error": f"Failed to delete: {str(del_exc)}"}), file=sys.stderr)
                        errors += 1
                    elif str(ve) == "NOT_A_DOG":
                        # Non-dog animal — remove from active_dogs and animals
                        aid = target.get("animal_id", "")
                        try:
                            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                            store.client.table("animals").delete().eq("animal_id", aid).execute()
                            store.client.table("system_prompts_v2").delete().eq("animal_id", aid).execute()
                            print(json.dumps({"animal_id": aid, "result": "removed_not_a_dog"}))
                        except Exception as del_exc:
                            print(json.dumps({"animal_id": aid, "error": f"Failed to delete NOT_A_DOG: {str(del_exc)}"}), file=sys.stderr)
                except Exception as exc:
                    errors += 1
                    print(json.dumps({"url": url, "error": str(exc)}), file=sys.stderr)

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
    raise SystemExit(main())
