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
cursor = conn.cursor()
cursor.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'system_prompts_v2';
""")
print(cursor.fetchall())
