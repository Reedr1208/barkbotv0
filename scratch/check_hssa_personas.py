import os
from supabase import create_client
import sys

url = os.environ.get("SUPABASE_URL") or os.environ.get("storage_SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(url, key)

res = supabase.table("active_dogs").select("animal_id").eq("shelter_id", "HSSA").execute()
hssa_active = {r["animal_id"] for r in res.data}

res2 = supabase.table("animal_persona_profiles").select("animal_id").execute()
all_personas = {r["animal_id"] for r in res2.data}

hssa_with_personas = hssa_active.intersection(all_personas)
print(f"Total HSSA active: {len(hssa_active)}")
print(f"HSSA with personas: {len(hssa_with_personas)}")
if len(hssa_with_personas) > 0:
    print(f"Sample HSSA dog with persona: {list(hssa_with_personas)[0]}")
