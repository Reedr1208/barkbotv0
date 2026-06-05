import os
import psycopg2

db_url = None
with open(".env.development.local", "r") as f:
    for line in f:
        if line.startswith("STORAGE_POSTGRES_URL_NON_POOLING="):
            db_url = line.split("=", 1)[1].strip().strip('"')
            break

if not db_url:
    print("Error: Could not find DB URL")
    exit(1)

print("Connecting to DB to reload schema cache...")
try:
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    cursor.execute("NOTIFY pgrst, 'reload schema';")
    conn.commit()
    print("Successfully notified PostgREST to reload schema.")
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals() and conn:
        cursor.close()
        conn.close()
