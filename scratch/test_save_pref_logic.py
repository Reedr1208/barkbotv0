import os
import psycopg2
from supabase import create_client

env_file = ".env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(supabase_url, supabase_key)

shelters_res = client.table("shelters").select("location_display_name").execute()
valid_locations = set([s["location_display_name"] for s in shelters_res.data]) if shelters_res.data else set()
valid_locations.add("any")

print("Valid locations from DB:", valid_locations)

location_input = "Tucson, AZ 🌵"
if location_input not in valid_locations:
    print(f"{location_input} rejected!")
else:
    print(f"{location_input} accepted!")
    
location_input2 = "New York, NY 🗽"
if location_input2 not in valid_locations:
    print(f"{location_input2} rejected!")
else:
    print(f"{location_input2} accepted!")
