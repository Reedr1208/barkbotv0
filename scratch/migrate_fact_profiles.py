import os
import psycopg2

env_file = ".env.development.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

postgres_url = os.environ.get("storage_POSTGRES_URL_NON_POOLING")
if not postgres_url:
    print("Postgres URL not found.")
    exit(1)

commands = [
    "ALTER TABLE animal_fact_profiles RENAME COLUMN sex_neuter_status TO sex;",
    "ALTER TABLE animal_fact_profiles RENAME COLUMN location_summary TO shelter_name;",
    "ALTER TABLE animal_fact_profiles ADD COLUMN age_bucket VARCHAR(255);",
    "ALTER TABLE animal_fact_profiles ADD COLUMN weight_class VARCHAR(255);",
    "ALTER TABLE animal_fact_profiles ADD COLUMN altered_status VARCHAR(255);",
    "ALTER TABLE animal_fact_profiles ADD COLUMN info_refreshed_at TIMESTAMPTZ;",
    "ALTER TABLE animal_fact_profiles DROP COLUMN image_public_url;"
]

conn = psycopg2.connect(postgres_url)
conn.autocommit = True
cur = conn.cursor()

for cmd in commands:
    print("Executing:", cmd)
    try:
        cur.execute(cmd)
        print("Success.")
    except Exception as e:
        print("Failed:", e)

cur.close()
conn.close()
