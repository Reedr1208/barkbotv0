import os
import sys
import psycopg2

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

try:
    conn = psycopg2.connect(db_url)
    print("Successfully connected to the database via PostgreSQL!")
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print("Database Version:", db_version)
    cursor.close()
    conn.close()
except Exception as e:
    print("Database Connection Error:", e)
