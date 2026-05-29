import os, json, psycopg2
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
db_url = os.environ.get("storage_POSTGRES_URL").split("?")[0]
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

cursor.execute("SELECT animal_id, shelter_id FROM active_dogs")
active_dogs = cursor.fetchall()
active_ids = {r[0] for r in active_dogs}

cursor.execute("SELECT animal_id, primary_archetype_key FROM animal_persona_profiles")
persona = cursor.fetchall()
persona_ids = {r[0] for r in persona}

valid_ids = list(active_ids.intersection(persona_ids))

pima_count = sum(1 for r in active_dogs if r[1] == "PIMA" and r[0] in valid_ids)
muddy_count = sum(1 for r in active_dogs if r[1] == "MUDDYPAWS" and r[0] in valid_ids)

print(f"Total valid: {len(valid_ids)}, PIMA: {pima_count}, MUDDYPAWS: {muddy_count}")

# Check system_prompts
cursor.execute("SELECT animal_id FROM system_prompts_v2")
prompts = {r[0] for r in cursor.fetchall()}
prompts_valid = [aid for aid in valid_ids if aid in prompts]
muddy_prompts = sum(1 for r in active_dogs if r[1] == "MUDDYPAWS" and r[0] in prompts_valid)
print(f"MuddyPaws dogs with prompts: {muddy_prompts}")
