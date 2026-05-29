import os, json
from supabase import create_client
import psycopg2

env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
db_url = os.environ.get("storage_POSTGRES_URL")
if "?" in db_url:
    db_url = db_url.split("?")[0]
conn = psycopg2.connect(db_url)
conn.autocommit = True
cursor = conn.cursor()
# Delete old V2 prompts where a V3 prompt exists
cursor.execute("""
    DELETE FROM system_prompts_v2
    WHERE prompt_version = 'v2' 
      AND animal_id IN (
          SELECT animal_id FROM system_prompts_v2 WHERE prompt_version = 'v3_test'
      );
""")
print(f"Deleted {cursor.rowcount} duplicate old v2 prompts.")
