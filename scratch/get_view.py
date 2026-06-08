import os, psycopg2
env_file = ".env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
conn = psycopg2.connect(db_url)
cursor = conn.cursor()
cursor.execute("SELECT definition FROM pg_views WHERE viewname = 'active_dogs';")
row = cursor.fetchone()
if row:
    print(row[0])
else:
    print("View not found in pg_views")
cursor.close()
conn.close()
