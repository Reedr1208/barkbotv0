"""Legacy entrypoint — delegates to jobs.shelters.mp.all."""
import logging
from jobs.shelters.mp.all import fetch_dogs, save_to_supabase

if __name__ == "__main__":
    logging.info("Starting scrape...")
    dogs = fetch_dogs()
    logging.info(f"Fetched {len(dogs)} dogs from MuddyPaws.")
    save_to_supabase(dogs)
    logging.info("Scrape completed successfully.")
