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

cursor.execute("SELECT animal_id, shelter_name FROM animals WHERE animal_id LIKE '%40960536%';")
for row in cursor.fetchall():
    print(f"animal_id: {row[0]}, shelter_name: {row[1]}")

cursor.execute("SELECT animal_id, shelter_id FROM active_dogs WHERE animal_id LIKE '%40960536%';")
for row in cursor.fetchall():
    print(f"active_dogs -> animal_id: {row[0]}, shelter_id: {row[1]}")

cursor.close()
conn.close()
