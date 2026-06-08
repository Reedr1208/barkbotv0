import os
import psycopg2

def fix_double_prefixes():
    env_file = ".env.development.local"
    with open(env_file, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
                
    db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
    conn = psycopg2.connect(db_url)
    # Set timeout to 0 for this session
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = 0;")
    cursor.execute("SET lock_timeout = 0;")
    
    try:
        constraints = [
            ("animal_fact_profiles", "animal_fact_profiles_animal_id_fkey"),
            ("system_prompts_v2", "system_prompts_v2_animal_id_fkey"),
            ("animal_persona_profiles", "animal_persona_profiles_animal_id_fkey"),
            ("saved_dogs", "saved_dogs_animal_id_fkey"),
            ("chat_conversations", "chat_conversations_animal_id_fkey"),
        ]
        
        print("Dropping constraints...")
        for table, constr in constraints:
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constr};")
            
        print("Deleting conflicting target IDs (the newly scraped ones)...")
        # For HSSA
        cursor.execute("""
            DELETE FROM active_dogs WHERE animal_id IN (
                SELECT REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') FROM animals WHERE animal_id LIKE 'HSSA-hssa-%'
            );
        """)
        for table, _ in constraints:
            cursor.execute(f"""
                DELETE FROM {table} WHERE animal_id IN (
                    SELECT REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') FROM animals WHERE animal_id LIKE 'HSSA-hssa-%'
                );
            """)
        cursor.execute("""
            DELETE FROM animals WHERE animal_id IN (
                SELECT REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') FROM animals WHERE animal_id LIKE 'HSSA-hssa-%'
            );
        """)
        
        # For NYCACC
        cursor.execute("""
            DELETE FROM active_dogs WHERE animal_id IN (
                SELECT REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') FROM animals WHERE animal_id LIKE 'NYCACC-nycacc-%'
            );
        """)
        for table, _ in constraints:
            cursor.execute(f"""
                DELETE FROM {table} WHERE animal_id IN (
                    SELECT REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') FROM animals WHERE animal_id LIKE 'NYCACC-nycacc-%'
                );
            """)
        cursor.execute("""
            DELETE FROM animals WHERE animal_id IN (
                SELECT REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') FROM animals WHERE animal_id LIKE 'NYCACC-nycacc-%'
            );
        """)
        
        print("Updating old IDs to correct IDs...")
        
        # HSSA updates
        cursor.execute("UPDATE active_dogs SET animal_id = REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') WHERE animal_id LIKE 'HSSA-hssa-%';")
        for table, _ in constraints:
            cursor.execute(f"UPDATE {table} SET animal_id = REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') WHERE animal_id LIKE 'HSSA-hssa-%';")
        cursor.execute("UPDATE animals SET animal_id = REPLACE(animal_id, 'HSSA-hssa-', 'HSSA-') WHERE animal_id LIKE 'HSSA-hssa-%';")
        
        # NYCACC updates
        cursor.execute("UPDATE active_dogs SET animal_id = REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') WHERE animal_id LIKE 'NYCACC-nycacc-%';")
        for table, _ in constraints:
            cursor.execute(f"UPDATE {table} SET animal_id = REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') WHERE animal_id LIKE 'NYCACC-nycacc-%';")
        cursor.execute("UPDATE animals SET animal_id = REPLACE(animal_id, 'NYCACC-nycacc-', 'NYCACC-') WHERE animal_id LIKE 'NYCACC-nycacc-%';")

        print("Recreating foreign key constraints...")
        cursor.execute("ALTER TABLE animal_fact_profiles ADD CONSTRAINT animal_fact_profiles_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;")
        cursor.execute("ALTER TABLE system_prompts_v2 ADD CONSTRAINT system_prompts_v2_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;")
        cursor.execute("ALTER TABLE animal_persona_profiles ADD CONSTRAINT animal_persona_profiles_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;")
        cursor.execute("ALTER TABLE saved_dogs ADD CONSTRAINT saved_dogs_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;")
        cursor.execute("ALTER TABLE chat_conversations ADD CONSTRAINT chat_conversations_animal_id_fkey FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;")

        conn.commit()
        print("Done fixing double prefixes.")

    except Exception as e:
        conn.rollback()
        print(f"Failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_double_prefixes()
