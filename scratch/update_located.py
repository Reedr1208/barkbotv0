import os, psycopg2
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

# Get MuddyPaws IDs
cursor.execute("SELECT animal_id FROM active_dogs WHERE shelter_id = 'MUDDYPAWS'")
m_ids = [r[0] for r in cursor.fetchall()]

if m_ids:
    cursor.execute("UPDATE animals SET located_at = 'MuddyPaws Rescue' WHERE animal_id = ANY(%s)", (m_ids,))
    conn.commit()
    print(f"Updated {cursor.rowcount} MuddyPaws dogs located_at.")
else:
    print("No MuddyPaws dogs found in active_dogs.")
