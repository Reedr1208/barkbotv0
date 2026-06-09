import os
import urllib.request
import json

env_file = ".env.development.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

req = urllib.request.Request(f"{supabase_url}/rest/v1/animal_fact_profiles?limit=1", headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        if data:
            print(data[0].keys())
        else:
            print("Table is empty")
except Exception as e:
    print(e)
