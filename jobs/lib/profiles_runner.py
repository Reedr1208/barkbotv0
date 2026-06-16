"""
Generic profile scraper runner.

Provides run_profiles_scrape() which encapsulates the main() loop
that was copy-pasted across every *_profiles.py:
  1. Parse args → get settings → create store
  2. Get least-recently-updated URLs
  3. For each URL: fetch → extract → upload image → save record
  4. Track stats → finish run

Each shelter only needs to provide a fetch_record callback.
"""

import argparse
import json
import sys
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from .store import BarkbotStore, Settings, get_settings, DEFAULT_DOGS_PER_RUN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    return parser.parse_args()


def run_profiles_scrape(
    shelter_id: str,
    fetch_record_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    *,
    dogs_per_run: int = DEFAULT_DOGS_PER_RUN,
    default_sleep: float = 1.0,
    max_execution_seconds: int = 240,
    fallback_url_fn: Callable[[str], str] | None = None,
    extra_fields: List[str] | None = None,
    headers: dict | None = None,
    on_http_error: Callable | None = None,
) -> int:
    """
    Generic profiles scraper main loop.

    Args:
        shelter_id: e.g. "PACC", "HSSA", "PAWSCH"
        fetch_record_fn: A function(url, target_dict) -> record_dict
            that fetches and parses a single dog profile.
        dogs_per_run: How many dogs to process per run.
        default_sleep: Default sleep between requests.
        max_execution_seconds: Stop after this many seconds.
        fallback_url_fn: Optional function(animal_id) -> url for missing URLs.
        extra_fields: Additional active_dogs fields to pass to targets.
        headers: Custom HTTP headers for image downloads.
        on_http_error: Optional callback(store, target, exc) for handling
            HTTP errors (e.g. deleting adopted dogs from active_dogs).

    Returns:
        0 on success (even with partial errors), raises on catastrophic failure.
    """
    args = parse_args()
    settings = get_settings(default_sleep=default_sleep)
    store = BarkbotStore(settings, headers=headers)

    targets = store.get_least_recently_updated_urls(
        shelter_id=shelter_id,
        limit=dogs_per_run,
        fallback_url_fn=fallback_url_fn,
        extra_fields=extra_fields,
    )

    if not targets:
        print(f"No adoptable {shelter_id} dogs found to scrape.")
        return 0

    print(f"Scraping the following {len(targets)} {shelter_id} dogs:")
    for t in targets:
        print(f" - {t['url']}")

    processed = inserted = updated = unchanged = errors = 0
    run_id = store.begin_run(args.triggered_by, len(targets))
    start_time = time.time()

    try:
        for target in targets:
            # Timeout check
            if time.time() - start_time > max_execution_seconds:
                print(f"Approaching timeout ({max_execution_seconds}s). Stopping early.", file=sys.stderr)
                break

            url = target["url"]
            if not url:
                continue

            processed += 1
            try:
                record = fetch_record_fn(url, target)

                # Fallback name/gender from active_dogs if extraction failed
                if not record.get("name") and target.get("name"):
                    record["name"] = target["name"]
                if not record.get("gender") and target.get("gender"):
                    record["gender"] = target["gender"]

                # Upload image
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

            except requests.exceptions.HTTPError as exc:
                errors += 1
                if on_http_error:
                    on_http_error(store, target, exc)
                else:
                    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)

            except ValueError as exc:
                if str(exc) == "NOT_A_DOG":
                    # Remove non-dogs from active_dogs
                    aid = target.get("animal_id", "")
                    try:
                        store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
                        print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_not_a_dog"}, ensure_ascii=False))
                    except Exception as del_exc:
                        print(json.dumps({"url": url, "error": f"Failed to delete NOT_A_DOG: {str(del_exc)}"}, ensure_ascii=False), file=sys.stderr)
                else:
                    errors += 1
                    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)

            except Exception as exc:
                errors += 1
                print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)

            time.sleep(settings.scrape_sleep_seconds)

        final_status = "success" if errors == 0 else "partial_success"
        store.finish_run(run_id, final_status, processed, inserted, updated, unchanged, errors)
        return 0
    except Exception as exc:
        store.finish_run(run_id, "failed", processed, inserted, updated, unchanged, errors + 1, notes=str(exc))
        raise
