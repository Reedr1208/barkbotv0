import os
import psycopg2
from supabase import create_client

env_file = ".env.development.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(supabase_url, supabase_key)

shelters_res = client.table("shelters").select("*").execute()
for s in shelters_res.data:
    print(s)
