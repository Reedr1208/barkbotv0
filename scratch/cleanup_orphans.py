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

tables = [
    "animal_fact_profiles",
    "system_prompts_v2",
    "animal_persona_profiles",
    "saved_dogs",
    "chat_conversations"
]

try:
    for table in tables:
        cursor.execute(f"SELECT DISTINCT animal_id FROM {table} WHERE NOT EXISTS (SELECT 1 FROM animals WHERE animals.animal_id = {table}.animal_id);")
        orphans = [r[0] for r in cursor.fetchall()]
        if orphans:
            print(f"Table {table} has {len(orphans)} orphaned animal_ids: {orphans}")
            cursor.execute(f"DELETE FROM {table} WHERE animal_id = ANY(%s)", (orphans,))
            print(f"Deleted orphans from {table}.")
    conn.commit()
    print("Orphan cleanup complete.")
except Exception as e:
    print("Error:", e)
    conn.rollback()
finally:
    cursor.close()
    conn.close()
