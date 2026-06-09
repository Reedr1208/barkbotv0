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
supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(supabase_url, supabase_key)

res = client.table("shelters").select("shelter_id, location_display_name, relative_path").execute()
for r in res.data:
    print(r)
