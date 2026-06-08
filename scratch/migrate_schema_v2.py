import os
import psycopg2

def run_migration():
    # Load env vars
    env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
    with open(env_file, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
                
    db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # Get active dogs to map shelter ids
    cursor.execute("SELECT animal_id, shelter_id FROM active_dogs")
    active_dogs_map = {r[0]: r[1] for r in cursor.fetchall()}

    # Get all animals
    cursor.execute("SELECT animal_id, url, located_at, description, bio, image_url FROM animals")
    animals = cursor.fetchall()

    try:
        # 1. Add new columns
        print("Adding new columns to animals...")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS shelter_profile_url TEXT;")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS shelter_name TEXT;")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS shelter_image_url TEXT;")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS city TEXT;")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS state TEXT;")
        cursor.execute("ALTER TABLE animals ADD COLUMN IF NOT EXISTS shelter_id TEXT;")
        
        # Adding bio_length generated column
        try:
            cursor.execute("ALTER TABLE animals ADD COLUMN bio_length INT GENERATED ALWAYS AS (LENGTH(COALESCE(bio, ''))) STORED;")
        except Exception as e:
            conn.rollback()
            print(f"Column bio_length might already exist: {e}")

        # 2. Drop constraints
        print("Dropping foreign key constraints...")
        constraints = [
            ("animal_fact_profiles", "animal_fact_profiles_animal_id_fkey"),
            ("system_prompts_v2", "system_prompts_v2_animal_id_fkey"),
            ("animal_persona_profiles", "animal_persona_profiles_animal_id_fkey")
        ]
        for table, constr in constraints:
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constr};")

        # 2.5 Drop old tables early to remove constraints
        print("Dropping old tables early...")
        cursor.execute("DROP TABLE IF EXISTS animal_versions;")
        cursor.execute("DROP TABLE IF EXISTS animal_change_events;")

        # 3. Migrate data
        print("Migrating data row by row...")
        for row in animals:
            old_id, url, located_at, description, bio, image_url = row
            
            shelter_id = active_dogs_map.get(old_id)
            if not shelter_id:
                # Infer from located_at or url
                loc = str(located_at).lower() if located_at else ""
                u = str(url).lower() if url else ""
                if "muddypaws" in loc or "muddypaws" in u:
                    shelter_id = "MP"
                elif "nycacc" in loc or "nycacc" in u:
                    shelter_id = "NYCACC"
                elif "hssa" in loc or "humane society" in loc or "hssa" in u:
                    shelter_id = "HSSA"
                elif "pima" in loc or "pima" in u:
                    shelter_id = "PACC"
                else:
                    print(f"WARNING: Could not infer shelter_id for {old_id}. Defaulting to PACC.")
                    shelter_id = "PACC"
            
            if shelter_id == "MUDDYPAWS":
                shelter_id = "MP"
            elif shelter_id == "PIMA":
                shelter_id = "PACC"
                
            city = "Tucson" if shelter_id in ("PACC", "HSSA") else "NYC"
            state = "AZ" if shelter_id in ("PACC", "HSSA") else "NY"
            
            # Create new animal ID
            new_id = f"{shelter_id.upper()}-{old_id}"
            if old_id.startswith(f"{shelter_id.upper()}-"):
                new_id = old_id # Already migrated?

            new_bio = ""
            if description and description.strip():
                new_bio += description.strip() + "\n\n"
            if bio and bio.strip():
                new_bio += bio.strip()
            new_bio = new_bio.strip()

            if new_id != old_id:
                # Update dependent tables
                cursor.execute("UPDATE animal_fact_profiles SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                cursor.execute("UPDATE system_prompts_v2 SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                cursor.execute("UPDATE animal_persona_profiles SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                cursor.execute("UPDATE saved_dogs SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                cursor.execute("UPDATE chat_conversations SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                cursor.execute("UPDATE active_dogs SET animal_id = %s WHERE animal_id = %s", (new_id, old_id))
                
                # We need to temporarily disable the primary key on animals to update it? 
                # Actually, UPDATE animals SET animal_id = ... works fine as long as no FK restricts it (we dropped them).
                pass
            
            cursor.execute("""
                UPDATE animals 
                SET animal_id = %s, shelter_profile_url = %s, shelter_name = %s, shelter_image_url = %s, 
                    city = %s, state = %s, shelter_id = %s, bio = %s
                WHERE animal_id = %s
            """, (new_id, url, located_at, image_url, city, state, shelter_id, new_bio, old_id))

        print("Data migration complete. Dropping old columns...")
        cols_to_drop = ["url", "located_at", "description", "data_updated", "image_url", "qa_status", "qa_notes"]
        for col in cols_to_drop:
            cursor.execute(f"ALTER TABLE animals DROP COLUMN IF EXISTS {col};")

        # Tables already dropped
        
        # 4. Recreate constraints
        print("Recreating foreign key constraints...")
        cursor.execute("""
            ALTER TABLE animal_fact_profiles 
            ADD CONSTRAINT animal_fact_profiles_animal_id_fkey 
            FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;
        """)
        cursor.execute("""
            ALTER TABLE system_prompts_v2 
            ADD CONSTRAINT system_prompts_v2_animal_id_fkey 
            FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;
        """)
        cursor.execute("""
            ALTER TABLE animal_persona_profiles 
            ADD CONSTRAINT animal_persona_profiles_animal_id_fkey 
            FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE;
        """)

        conn.commit()
        print("Migration finished successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_migration()
