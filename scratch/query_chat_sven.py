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

cursor.execute("SELECT animal_id, dog_name FROM chat_conversations WHERE dog_name ILIKE '%Sven%';")
for row in cursor.fetchall():
    print(f"chat_conversations -> animal_id: {row[0]}, dog_name: {row[1]}")

cursor.execute("SELECT animal_id, dog_name FROM saved_dogs WHERE dog_name ILIKE '%Sven%';")
for row in cursor.fetchall():
    print(f"saved_dogs -> animal_id: {row[0]}, dog_name: {row[1]}")

cursor.close()
conn.close()
