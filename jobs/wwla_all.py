"""Legacy entrypoint — delegates to jobs.shelters.wwla.all."""
import logging
from jobs.shelters.wwla.all import fetch_html, parse_records, save_to_supabase, LISTING_URL

if __name__ == "__main__":
    logging.info("Starting WWLA scrape...")
    html = fetch_html(LISTING_URL)
    dogs = parse_records(html)
    logging.info(f"Fetched {len(dogs)} dogs from WWLA.")
    save_to_supabase(dogs)
    logging.info("WWLA Scrape completed successfully.")
