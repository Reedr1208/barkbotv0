import os
import requests
from supabase import create_client

def main():
    from pathlib import Path
    env_local = Path('.env.local')
    if env_local.exists():
        with open(env_local) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v.strip().strip('"').strip("'")
    
    supabase = create_client(os.environ["storage_SUPABASE_URL"], os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"])
    
    resp = supabase.table("active_dogs").select("animal_id, name").eq("shelter_id", "HSSA").execute()
    print(f"Total HSSA dogs in active_dogs: {len(resp.data)}")
    
    # We can fetch the Adopt-a-Pet API directly for each active dog to accurately check the species!
    # Or just use the URL heuristic, but active_dogs doesn't store the URL.
    # We can fetch https://www.adoptapet.com/pet/{numeric_id} and look at petSpeciesId
    
    non_dogs = []
    
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from jobs.lib_hssa_parser import extract_pet_details

    for row in resp.data:
        numeric_id = row["animal_id"].replace("hssa-", "")
        url = f"https://www.adoptapet.com/pet/{numeric_id}"
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                pet = extract_pet_details(r.text)
                species_id = pet.get("petSpeciesId")
                if species_id != 1:
                    print(f"{row['name']} is NOT a dog (speciesId={species_id})")
                    non_dogs.append(row["animal_id"])
        except Exception as e:
            print(f"Failed to fetch {row['animal_id']}: {e}")
            
    print(f"Identified {len(non_dogs)} non-dogs.")
    
    if non_dogs:
        print("Deleting them from active_dogs...")
        supabase.table("active_dogs").delete().in_("animal_id", non_dogs).execute()
        print("Done deleting.")

if __name__ == "__main__":
    main()
