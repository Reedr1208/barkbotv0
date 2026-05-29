import os, psycopg2

env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
db_url = os.environ.get("storage_POSTGRES_URL")
if "?" in db_url:
    db_url = db_url.split("?")[0]
conn = psycopg2.connect(db_url)
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("DELETE FROM system_prompts_v2;")
print(f"Deleted {cursor.rowcount} rows from system_prompts_v2.")

cursor.execute("DELETE FROM animal_persona_profiles;")
print(f"Deleted {cursor.rowcount} rows from animal_persona_profiles.")
