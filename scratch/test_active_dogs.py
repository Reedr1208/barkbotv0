import os
from supabase import create_client

env_file = ".env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

supabase_url = os.environ["storage_SUPABASE_URL"].split("?")[0]
supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
client = create_client(supabase_url, supabase_key)

try:
    res = client.table("active_dogs").select("*").limit(1).execute()
    print("Success:", len(res.data))
except Exception as e:
    print("Error:", e)
