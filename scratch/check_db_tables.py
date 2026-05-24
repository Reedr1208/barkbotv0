import os
import sys
import psycopg2
from urllib.parse import urlparse, urlunparse

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

db_url = os.environ.get("STORAGE_POSTGRES_URL") or os.environ.get("storage_POSTGRES_URL")
if not db_url:
    print("Error: No database connection URL found.")
    sys.exit(1)

parsed = urlparse(db_url)
cleaned_url = urlunparse((
    parsed.scheme,
    parsed.netloc,
    parsed.path,
    parsed.params,
    "", # No query parameters
    parsed.fragment
))

try:
    conn = psycopg2.connect(cleaned_url)
    cursor = conn.cursor()
    
    # List all tables in public schema
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = [r[0] for r in cursor.fetchall()]
    print("All tables in 'public' schema:")
    print(tables)
    
    cursor.close()
    conn.close()
except Exception as e:
    print("Error:", e)
