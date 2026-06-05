import re

with open("jobs/05_scrape_hssa_profiles.py", "r") as f:
    hssa_content = f.read()

# extract Settings, get_settings, BarkbotStore, record_hash, compute_diff, download_image_bytes
store_code_match = re.search(r"(TRACKED_FIELDS = \[.*?\]\n\nDOGS_PER_RUN = 30\n\n@dataclass\nclass Settings:.*?)def parse_args", hssa_content, re.DOTALL)
if not store_code_match:
    raise Exception("Could not find store code")

store_code = store_code_match.group(1)

# Modify get_least_recently_updated_hssa_dogs to nycacc
store_code = store_code.replace("get_least_recently_updated_hssa_dogs", "get_least_recently_updated_nycacc_dogs")
store_code = store_code.replace('"HSSA"', '"NYCACC"')
store_code = store_code.replace('numeric_id = aid.replace("hssa-", "")', 'numeric_id = aid.replace("nycacc-", "")')
store_code = store_code.replace('url": f"https://www.adoptapet.com/pet/{numeric_id}"', 'url": f"https://nycacc.app/#/browse/{numeric_id}"')

with open("jobs/07_scrape_nycacc_profiles.py", "r") as f:
    nycacc_content = f.read()

# Prepend imports and store code
imports_addition = """
import os
import hashlib
import requests
from supabase import create_client
from typing import Tuple
"""

nycacc_content = re.sub(
    r"(from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError)",
    r"\1\n" + imports_addition + "\n" + store_code,
    nycacc_content
)

# Now rewrite main_async
main_async_new = """async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    store = BarkbotStore(settings)
    
    dogs = store.get_least_recently_updated_nycacc_dogs(limit=DOGS_PER_RUN)
    if not dogs:
        print("No adoptable NYCACC dogs found to scrape.")
        return 0

    native_ids = [d["numeric_id"] for d in dogs]

    print(f"Scraping {len(native_ids)} NYCACC dogs.")

    if "VERCEL" in os.environ or "storage_SUPABASE_URL" in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/ms-playwright"
        os.system("python -m playwright install chromium")

    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run("cron_nycacc_profiles", len(dogs))

    start_time = time.time()
    max_time = 230  # 4 mins limit, leave some buffer

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                f"--window-size={args.width},{args.height}",
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            viewport={"width": args.width, "height": args.height},
            screen={"width": args.width, "height": args.height},
            device_scale_factor=1,
            service_workers="block",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        await context.add_init_script(FETCH_INTERCEPTOR_JS)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = await context.new_page()

        collector = NetworkCollector()
        collector.attach(page)

        try:
            logs, payloads = await load_app_and_collect_feed(page, collector, native_ids[0], args)

            for native_id in native_ids:
                if time.time() - start_time > max_time:
                    print("Reached 4-minute limit, breaking early.")
                    break
                    
                processed += 1
                pet, feed_updated = find_pet_in_payloads(payloads, native_id)
                adopets_link = ""
                if args.include_adopets_link:
                    try:
                        adopets_link = await collect_adopets_status(page, native_id, logs)
                    except Exception as e:
                        print(f"  WARNING: could not fetch adopets link for {native_id}: {e}")

                if pet is None:
                    print(f"  WARNING: no matching pet found for {native_id}")
                    errors += 1
                    # Remove from active_dogs if not found
                    aid = f"nycacc-{native_id}"
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_not_found"}, ensure_ascii=False))
                    except Exception as e:
                        pass
                    continue
                
                # Format into Barkbot structure
                raw_row = build_output_row(
                    pet,
                    native_id,
                    feed_updated=feed_updated,
                    adopets_link=adopets_link,
                    include_photo_urls=args.include_photo_urls,
                )
                
                record = {
                    "animal_id": raw_row["animal_id"],
                    "url": raw_row["url"],
                    "located_at": raw_row["located_at"],
                    "weight": raw_row["weight"],
                    "age": raw_row["age"],
                    "description": raw_row["description"],
                    "data_updated": now_iso(),
                    "image_url": first_image_from_pet(pet), # Need to implement this
                    "bio": html_to_text(pet.get("summaryHtml")), # fallback bio
                    "more_info": "",
                }

                try:
                    import urllib.request
                    # Upload image
                    image_file, image_public_url = store.upload_image(record["animal_id"], record.get("image_url"))
                    record["image_file"] = image_file
                    record["image_public_url"] = image_public_url
                    
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
                    print(json.dumps({"animal_id": record["animal_id"], "error": str(exc)}, ensure_ascii=False))
                    
        finally:
            await browser.close()
            
        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)

    return 0

def first_image_from_pet(pet: dict) -> str:
    photos = pet.get("photos")
    if isinstance(photos, list) and photos:
        for p in photos:
            if isinstance(p, str) and p.startswith("http"):
                return p
    return ""
"""

nycacc_content = re.sub(r"async def main_async.*?def build_arg_parser", main_async_new + "\ndef build_arg_parser", nycacc_content, flags=re.DOTALL)

with open("jobs/07_scrape_nycacc_profiles.py", "w") as f:
    f.write(nycacc_content)
