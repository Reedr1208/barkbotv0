import os
import psycopg2

db_urls = []
with open(".env.development.local", "r") as f:
    for line in f:
        if "POSTGRES_URL_NON_POOLING=" in line:
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            if url not in db_urls:
                db_urls.append(url)

for db_url in db_urls:
    print(f"Connecting to DB: {db_url.split('@')[1].split('/')[0]}...")
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("Adding intro_summary to animal_fact_profiles...")
        cursor.execute("ALTER TABLE animal_fact_profiles ADD COLUMN IF NOT EXISTS intro_summary TEXT;")
        
        print("Dropping intro_summary from system_prompts_v2...")
        cursor.execute("ALTER TABLE system_prompts_v2 DROP COLUMN IF EXISTS intro_summary;")
        
        print("Reloading PostgREST schema cache...")
        cursor.execute("NOTIFY pgrst, 'reload schema';")
        
        conn.commit()
        print("Success for this DB.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
    print("---")
