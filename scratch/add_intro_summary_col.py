import os
import psycopg2

db_url = None
with open(".env.development.local", "r") as f:
    for line in f:
        if line.startswith("STORAGE_POSTGRES_URL_NON_POOLING="):
            db_url = line.split("=", 1)[1].strip().strip('"')
            break

if not db_url:
    print("Error: Could not find STORAGE_POSTGRES_URL_NON_POOLING in .env.development.local")
    exit(1)

print("Connecting to database...")
try:
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    print("Adding intro_summary column...")
    cursor.execute("ALTER TABLE system_prompts_v2 ADD COLUMN IF NOT EXISTS intro_summary TEXT;")
    conn.commit()
    
    # Check if column exists
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='system_prompts_v2' AND column_name='intro_summary';")
    col = cursor.fetchone()
    if col:
        print("Success! intro_summary column exists.")
    else:
        print("Failed to add column.")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals() and conn:
        cursor.close()
        conn.close()
