"""Legacy entrypoint — delegates to jobs.shelters.pacc.inventory."""
from jobs.shelters.pacc.inventory import scrape_all_dogs, save_to_supabase

if __name__ == "__main__":
    dogs = scrape_all_dogs()
    save_to_supabase(dogs)
    print(f"Done. Wrote {len(dogs)} dogs to active_dogs table in Supabase.")
