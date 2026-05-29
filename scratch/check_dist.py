import os, json, psycopg2
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
cursor = conn.cursor()
cursor.execute("SELECT primary_archetype_key, COUNT(*) AS total_count FROM animal_persona_profiles GROUP BY 1 ORDER BY 2 ASC")
dist = dict(cursor.fetchall())
print(json.dumps(dist, indent=2))
