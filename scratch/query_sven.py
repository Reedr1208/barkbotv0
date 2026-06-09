import os
import psycopg2

env_file = ".env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

cursor.execute("SELECT animal_id, name, shelter_name FROM animals WHERE name ILIKE '%Sven%';")
for row in cursor.fetchall():
    print(f"animal_id: {row[0]}, name: {row[1]}, shelter_name: {row[2]}")

cursor.execute("SELECT animal_id, name, shelter_id FROM active_dogs WHERE name ILIKE '%Sven%';")
for row in cursor.fetchall():
    print(f"active_dogs -> animal_id: {row[0]}, name: {row[1]}, shelter_id: {row[2]}")

cursor.close()
conn.close()
