import os
import psycopg2

db_url = None
with open(".env.development.local", "r") as f:
    for line in f:
        if line.startswith("STORAGE_POSTGRES_URL_NON_POOLING="):
            db_url = line.split("=", 1)[1].strip().strip('"')
            break

if not db_url:
    print("Error: DB URL not found")
    exit(1)

try:
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    tables = ['system_prompts_v2', 'animal_fact_profiles']
    for table in tables:
        print(f"Table: {table}")
        cursor.execute(f"SELECT column_name, column_default FROM information_schema.columns WHERE table_name = '{table}' AND column_name IN ('created_at', 'updated_at');")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  {row[0]}: default = {row[1]}")
        
        print("Triggers:")
        cursor.execute(f"SELECT trigger_name, action_statement FROM information_schema.triggers WHERE event_object_table = '{table}';")
        triggers = cursor.fetchall()
        for t in triggers:
            print(f"  {t[0]}: {t[1]}")
            
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals() and conn:
        cursor.close()
        conn.close()
