import os, psycopg2, random
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
active_res = cursor.fetchall()
active_dogs = {r[0]: {"shelter_id": r[1]} for r in active_res}

cursor.execute("SELECT animal_id, primary_archetype_key FROM animal_persona_profiles")
persona_res = cursor.fetchall()
persona_data = {r[0]: {"primary_archetype_key": r[1]} for r in persona_res}

valid_ids = list(set(active_dogs.keys()).intersection(persona_data.keys()))

last_2_archetypes = set()
scored_dogs = {}
for aid in valid_ids:
    score = 0
    dog_arch = persona_data[aid].get("primary_archetype_key")
    if dog_arch and dog_arch not in last_2_archetypes:
        score += 0.5
    scored_dogs[aid] = score

max_score = max(scored_dogs.values()) if scored_dogs else 0
best_candidates = [aid for aid, score in scored_dogs.items() if score == max_score]

pima = 0
muddy = 0
for _ in range(100):
    c = random.choice(best_candidates)
    if active_dogs[c]["shelter_id"] == "PIMA":
        pima += 1
    else:
        muddy += 1

print(f"Valid IDs: {len(valid_ids)}")
print(f"Best Candidates: {len(best_candidates)}")
print(f"PIMA vs MUDDY ratio in best candidates: {sum(1 for c in best_candidates if active_dogs[c]['shelter_id'] == 'PIMA')} / {sum(1 for c in best_candidates if active_dogs[c]['shelter_id'] == 'MUDDYPAWS')}")
print(f"Simulated 100 draws: {pima} PIMA, {muddy} MUDDYPAWS")
