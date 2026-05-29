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

try:
    print("Renaming pima_all_dogs to active_dogs...")
    cursor.execute("ALTER TABLE pima_all_dogs RENAME TO active_dogs;")
except Exception as e:
    print(f"Error renaming table: {e}")

try:
    print("Adding shelter_id to active_dogs...")
    cursor.execute("ALTER TABLE active_dogs ADD COLUMN shelter_id VARCHAR(50) DEFAULT 'PIMA';")
except Exception as e:
    print(f"Error adding shelter_id: {e}")

try:
    print("Adding raw_data_jsonb to animals...")
    cursor.execute("ALTER TABLE animals ADD COLUMN raw_data_jsonb JSONB;")
except Exception as e:
    print(f"Error adding raw_data_jsonb: {e}")

print("Migration complete!")
