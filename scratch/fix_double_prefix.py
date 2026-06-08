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
    cursor = conn.cursor()

    try:
        # Get all animals with double prefixes
        cursor.execute("SELECT animal_id FROM animals WHERE animal_id LIKE 'HSSA-hssa-%' OR animal_id LIKE 'NYCACC-nycacc-%'")
        bad_records = [r[0] for r in cursor.fetchall()]
        
        print(f"Found {len(bad_records)} bad records.")

        # Drop constraints to allow animal_id modification
        constraints = [
            ("animal_fact_profiles", "animal_fact_profiles_animal_id_fkey"),
            ("system_prompts_v2", "system_prompts_v2_animal_id_fkey"),
            ("animal_persona_profiles", "animal_persona_profiles_animal_id_fkey"),
            ("saved_dogs", "saved_dogs_animal_id_fkey"),
            ("chat_conversations", "chat_conversations_animal_id_fkey"),
        ]
        for table, constr in constraints:
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constr};")

        for bad_id in bad_records:
            # Determine correct id
            if bad_id.startswith("HSSA-hssa-"):
                correct_id = bad_id.replace("HSSA-hssa-", "HSSA-")
            elif bad_id.startswith("NYCACC-nycacc-"):
                correct_id = bad_id.replace("NYCACC-nycacc-", "NYCACC-")
            else:
                continue
                
            print(f"Fixing {bad_id} -> {correct_id}")

            # Check if correct_id already exists in animals
            cursor.execute("SELECT 1 FROM animals WHERE animal_id = %s", (correct_id,))
            exists = cursor.fetchone() is not None

            if exists:
                # If the correct one exists, we should delete the NEW one (the correct_id) 
                # because the OLD one (bad_id) holds the historical data (personas, chats, etc.)
                # But wait, maybe the new one has fresher data.
                # Let's delete the new one from animals, then rename the old one to correct_id.
                # First delete from active_dogs if it exists (it's just a view or table?)
                # active_dogs is a table or view? We checked earlier, it's a BASE TABLE!
                # So delete from active_dogs where animal_id = correct_id
                cursor.execute("DELETE FROM active_dogs WHERE animal_id = %s", (correct_id,))
                
                # We also need to delete any related records that might have been created for the new correct_id
                for table, _ in constraints:
                    cursor.execute(f"DELETE FROM {table} WHERE animal_id = %s", (correct_id,))
                cursor.execute("DELETE FROM animals WHERE animal_id = %s", (correct_id,))
            
            # Now update the old one to the correct one
            # Also update active_dogs
            cursor.execute("UPDATE active_dogs SET animal_id = %s WHERE animal_id = %s", (correct_id, bad_id))
            
            # Update related tables
            for table, _ in constraints:
                cursor.execute(f"UPDATE {table} SET animal_id = %s WHERE animal_id = %s", (correct_id, bad_id))
                
            # Update the main animals table
            cursor.execute("UPDATE animals SET animal_id = %s WHERE animal_id = %s", (correct_id, bad_id))

        # Recreate constraints
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
