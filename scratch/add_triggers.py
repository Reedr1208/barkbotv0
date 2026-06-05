import os
import psycopg2

sql_script = """
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_system_prompts_v2_modtime ON system_prompts_v2;
CREATE TRIGGER update_system_prompts_v2_modtime
  BEFORE UPDATE ON system_prompts_v2
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_animal_fact_profiles_modtime ON animal_fact_profiles;
CREATE TRIGGER update_animal_fact_profiles_modtime
  BEFORE UPDATE ON animal_fact_profiles
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
"""

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
        
        print("Applying trigger functions...")
        cursor.execute(sql_script)
        
        conn.commit()
        print("Success for this DB.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
    print("---")
