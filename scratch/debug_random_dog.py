import sys
import os
from pathlib import Path
sys.path.insert(0, 'api')

env_local = Path('.env.development.local')
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

from supabase import create_client
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

# Fetch shelters
shelters_res = client.table("shelters").select("*").execute()
shelters_map = {s["shelter_id"]: s for s in shelters_res.data} if shelters_res.data else {}

# Fetch active dogs
active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id").execute()
active_dogs = {row["animal_id"]: row for row in active_res.data}

print("PACC Shelter Location Name:")
pacc_shelter = shelters_map.get("PACC")
print(pacc_shelter.get("location_display_name"))

print("Does 'tucson, az 🌵' == dog_loc.lower()?")
dog_loc = pacc_shelter.get("location_display_name", "")
pref_loc = "tucson, az 🌵"
print(f"pref_loc: '{pref_loc}'")
print(f"dog_loc.lower(): '{dog_loc.lower()}'")
print(f"Match: {pref_loc == dog_loc.lower()}")
