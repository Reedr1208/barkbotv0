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

try:
    print("Adding columns to animals...")
    cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS name text;")
    cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS gender text;")
    
    print("Adding columns to active_dogs...")
    cursor.execute("ALTER TABLE active_dogs ADD COLUMN IF NOT EXISTS city text;")
    cursor.execute("ALTER TABLE active_dogs ADD COLUMN IF NOT EXISTS state text;")
    cursor.execute("ALTER TABLE active_dogs ADD COLUMN IF NOT EXISTS shelter_name text;")
    
    print("Normalizing shelter IDs in active_dogs...")
    cursor.execute("UPDATE active_dogs SET shelter_id = 'PACC' WHERE shelter_id = 'PIMA';")
    cursor.execute("UPDATE active_dogs SET shelter_id = 'MP' WHERE shelter_id = 'MUDDYPAWS';")
    
    print("Cleaning up names in active_dogs...")
    cursor.execute("UPDATE active_dogs SET name = INITCAP(TRIM(REPLACE(name, '*', '')));")
    
    print("Mapping city, state, shelter_name in active_dogs...")
    cursor.execute("UPDATE active_dogs SET city = 'Tucson', state = 'AZ', shelter_name = 'Pima Animal Care Center' WHERE shelter_id = 'PACC';")
    cursor.execute("UPDATE active_dogs SET city = 'Tucson', state = 'AZ', shelter_name = 'Humane Society of Southern Arizona' WHERE shelter_id = 'HSSA';")
    cursor.execute("UPDATE active_dogs SET city = 'New York', state = 'NY', shelter_name = 'Animal Care Centers of NYC' WHERE shelter_id = 'NYCACC';")
    cursor.execute("UPDATE active_dogs SET city = 'New York', state = 'NY', shelter_name = 'Muddy Paws Rescue' WHERE shelter_id = 'MP';")
    
    print("Backfilling animals table with name and gender from active_dogs...")
    cursor.execute('''
        UPDATE animals a
        SET name = ad.name, gender = ad.gender
        FROM active_dogs ad
        WHERE a.animal_id = ad.animal_id;
    ''')
    
    print("Dropping deprecated columns from active_dogs...")
    cursor.execute("ALTER TABLE active_dogs DROP COLUMN IF EXISTS location;")
    cursor.execute("ALTER TABLE active_dogs DROP COLUMN IF EXISTS view_type;")
    cursor.execute("ALTER TABLE active_dogs DROP COLUMN IF EXISTS image_url;")
    
    conn.commit()
    print("Database migration complete.")
    
    # Reload Supabase PostgREST schema cache
    cursor.execute("NOTIFY pgrst, 'reload schema';")
    conn.commit()

except Exception as e:
    print(f"Error during migration: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
