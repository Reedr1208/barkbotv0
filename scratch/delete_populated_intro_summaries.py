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
        
        # Check how many we are going to delete
        cursor.execute("SELECT count(*) FROM animal_fact_profiles WHERE intro_summary IS NOT NULL AND intro_summary != '';")
        count = cursor.fetchone()[0]
        print(f"Found {count} fact profiles with a non-empty intro_summary.")
        
        if count > 0:
            print("Deleting from system_prompts_v2...")
            cursor.execute("""
                DELETE FROM system_prompts_v2 
                WHERE animal_id IN (
                    SELECT animal_id FROM animal_fact_profiles 
                    WHERE intro_summary IS NOT NULL AND intro_summary != ''
                );
            """)
            deleted_prompts = cursor.rowcount
            print(f"Deleted {deleted_prompts} system_prompts_v2 records.")
            
            print("Deleting from animal_fact_profiles...")
            cursor.execute("DELETE FROM animal_fact_profiles WHERE intro_summary IS NOT NULL AND intro_summary != '';")
            deleted_facts = cursor.rowcount
            print(f"Deleted {deleted_facts} animal_fact_profiles records.")
            
            conn.commit()
            print("Deletions committed.")
        else:
            print("Nothing to delete.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
    print("---")
