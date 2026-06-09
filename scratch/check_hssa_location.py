import os
from dotenv import load_dotenv
load_dotenv(".env.local")
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

res = supabase.table("shelters").select("shelter_id, location_display_name, city, state").execute()
for r in res.data:
    print(r)
