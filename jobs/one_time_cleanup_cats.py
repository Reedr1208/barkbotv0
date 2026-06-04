import os
import requests
from supabase import create_client
import sys
import json
import time

# Ensure we can import lib_hssa_parser
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from lib_hssa_parser import extract_pet_details

def main():
    print("Starting one-time cleanup of non-dogs from HSSA...")
    supabase = create_client(os.environ["storage_SUPABASE_URL"], os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"])
    
    resp = supabase.table("active_dogs").select("animal_id, name").eq("shelter_id", "HSSA").execute()
    print(f"Total HSSA dogs in active_dogs table: {len(resp.data)}")
    
    non_dogs = []
    
    for row in resp.data:
        numeric_id = row["animal_id"].replace("hssa-", "")
        url = f"https://www.adoptapet.com/pet/{numeric_id}"
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                pet = extract_pet_details(r.text)
                species_id = pet.get("petSpeciesId")
                
                if species_id is not None and species_id != 1:
                    print(f"{row['name']} is NOT a dog (speciesId={species_id})")
                    non_dogs.append(row["animal_id"])
            elif r.status_code in (404, 410):
                print(f"{row['name']} returned 404. It will be removed naturally by the profile scraper.")
        except Exception as e:
            print(f"Failed to fetch {row['animal_id']}: {e}")
        time.sleep(0.5) # respect rate limits
            
    print(f"Identified {len(non_dogs)} non-dogs by checking Adopt-a-Pet API directly.")
    
    if non_dogs:
        print("Deleting them from active_dogs table...")
        supabase.table("active_dogs").delete().in_("animal_id", non_dogs).execute()
        
        print("Deleting them from animals table (if they were already saved)...")
        supabase.table("animals").delete().in_("animal_id", non_dogs).execute()
        
        print("Done deleting non-dogs.")
    else:
        print("No non-dogs found to delete.")

if __name__ == "__main__":
    main()
