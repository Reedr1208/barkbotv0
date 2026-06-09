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

# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS shelters (
    shelter_id TEXT PRIMARY KEY,
    shelter_name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    location_name TEXT NOT NULL,
    location_display_name TEXT NOT NULL
);
""")

# Insert initial records
records = [
    ("PACC", "Pima Animal Care Center", "Tucson", "AZ", "Tucson, AZ", "Tucson, AZ 🌵"),
    ("HSSA", "Humane Society of Southern Arizona", "Tucson", "AZ", "Tucson, AZ", "Tucson, AZ 🌵"),
    ("NYCACC", "Animal Care Centers of NYC", "NYC", "NY", "NYC, NY", "New York, NY 🗽"),
    ("MP", "Muddy Paws Rescue", "NYC", "NY", "NYC, NY", "New York, NY 🗽")
]

cursor.executemany("""
INSERT INTO shelters (shelter_id, shelter_name, city, state, location_name, location_display_name)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (shelter_id) DO UPDATE SET
    shelter_name = EXCLUDED.shelter_name,
    city = EXCLUDED.city,
    state = EXCLUDED.state,
    location_name = EXCLUDED.location_name,
    location_display_name = EXCLUDED.location_display_name;
""", records)

conn.commit()
print("Successfully created and populated shelters table!")

cursor.close()
conn.close()
