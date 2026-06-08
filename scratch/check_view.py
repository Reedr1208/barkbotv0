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
try:
    cursor.execute("SELECT * FROM active_dogs LIMIT 1;")
    print("active_dogs view exists!")
except Exception as e:
    print("Error:", e)
cursor.close()
conn.close()
