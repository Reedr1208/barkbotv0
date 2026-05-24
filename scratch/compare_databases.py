import os
import sys

sys.path.append("/Users/chayev/repos/Reedr1208/barkbotv0")
env_file = "/Users/chayev/repos/Reedr1208/barkbotv0/.env.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                os.environ[key] = val

storage_url = os.environ.get("storage_SUPABASE_URL")
general_url = os.environ.get("SUPABASE_URL")

print("storage_SUPABASE_URL:", storage_url)
print("SUPABASE_URL:", general_url)

storage_pg = os.environ.get("storage_POSTGRES_URL")
general_pg = os.environ.get("STORAGE_POSTGRES_URL")

print("storage_POSTGRES_URL:", storage_pg)
print("STORAGE_POSTGRES_URL:", general_pg)
