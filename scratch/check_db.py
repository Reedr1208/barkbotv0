import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(url, key)

res = supabase.table("animal_persona_profiles").select("count", count="exact").execute()
print(f"Total persona profiles: {res.count}")

active_res = supabase.table("animal_persona_profiles").select("count", count="exact").eq("archived", False).execute()
print(f"Active persona profiles: {active_res.count}")
