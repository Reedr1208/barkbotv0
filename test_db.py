import os, json
from supabase import create_client
with open('.env.local') as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v.strip().strip('"').strip("'")
c = create_client(os.environ["storage_SUPABASE_URL"], os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"])
print(json.dumps(c.table('active_dogs').select('*').limit(1).execute().data, indent=2))
