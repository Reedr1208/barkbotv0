"""
HSSA (Humane Society of Southern Arizona) — Profile Scraper

Fetches detailed profiles from adoptapet.com using the HSSA parser,
then upserts them into the animals table.
"""

import json
import sys
from typing import Any, Dict

import requests

from jobs.shelters.hssa.parser import build_record, extension_from_response_or_url
from jobs.lib.profiles_runner import run_profiles_scrape

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_record(url: str, target: dict) -> Dict[str, Any]:
    """Fetch an HSSA profile page and extract the record."""
    numeric_id = target.get("animal_id", "").replace("HSSA-", "")
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    record = build_record(response.text, pet_id=numeric_id)
    record["image_file"] = None
    record["image_public_url"] = None
    record["name"] = target.get("name")
    record["gender"] = target.get("gender")
    return record


def on_http_error(store, target, exc):
    """Handle HTTP errors — remove adopted dogs from active_dogs."""
    aid = target.get("animal_id", "")
    url = target.get("url", "")
    if exc.response.status_code in (404, 500, 410):
        try:
            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
            print(json.dumps({
                "animal_id": aid,
                "result": "removed_from_active_dogs_due_to_http_error",
                "status_code": exc.response.status_code,
            }, ensure_ascii=False))
        except Exception as del_exc:
            print(json.dumps({
                "url": url,
                "error": f"Failed to delete after HTTP {exc.response.status_code}: {str(del_exc)}",
            }, ensure_ascii=False), file=sys.stderr)
    else:
        print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)


def fallback_url(animal_id: str) -> str:
    numeric_id = animal_id.replace("HSSA-", "")
    return f"https://www.adoptapet.com/pet/{numeric_id}"


def main() -> int:
    return run_profiles_scrape(
        shelter_id="HSSA",
        fetch_record_fn=fetch_record,
        default_sleep=1.5,
        fallback_url_fn=fallback_url,
        headers=HEADERS,
        on_http_error=on_http_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
