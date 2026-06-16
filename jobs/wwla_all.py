"""Legacy entrypoint — delegates to jobs.shelters.wwla.all."""
import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.shelters.wwla.all import fetch_html, parse_records, save_to_supabase, LISTING_URL

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Starting WWLA scrape...")
    html = fetch_html(LISTING_URL)
    dogs = parse_records(html)
    logging.info(f"Fetched {len(dogs)} dogs from WWLA.")
    save_to_supabase(dogs)
    logging.info("WWLA Scrape completed successfully.")
