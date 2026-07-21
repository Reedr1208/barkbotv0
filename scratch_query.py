import os
import time
import json
from concurrent.futures import ThreadPoolExecutor
from supabase import create_client

with open('.env.local') as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v.strip().strip('"').strip("'")

c = create_client(os.environ["storage_SUPABASE_URL"], os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"])

def fetch_all_rows(query_builder, page_size=1000):
    all_data = []
    offset = 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        all_data.extend(res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    return all_data

def test_sequential():
    t0 = time.time()
    active = fetch_all_rows(c.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id"))
    shelters = c.table("shelters").select("*").execute().data
    personas = fetch_all_rows(c.table("animal_persona_profiles").select("animal_id, primary_archetype_key, updated_at"))
    facts = fetch_all_rows(c.table("animal_fact_profiles").select("animal_id, age_bucket, weight_class"))
    t1 = time.time()
    print(f"Sequential fetch_all_rows took: {t1 - t0:.2f} seconds. Active: {len(active)}, Shelters: {len(shelters)}, Personas: {len(personas)}, Facts: {len(facts)}")

def test_parallel():
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as executor:
        f_active = executor.submit(fetch_all_rows, c.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id"))
        f_shelters = executor.submit(lambda: c.table("shelters").select("*").execute().data)
        f_personas = executor.submit(fetch_all_rows, c.table("animal_persona_profiles").select("animal_id, primary_archetype_key, updated_at"))
        f_facts = executor.submit(fetch_all_rows, c.table("animal_fact_profiles").select("animal_id, age_bucket, weight_class"))
        
        active = f_active.result()
        shelters = f_shelters.result()
        personas = f_personas.result()
        facts = f_facts.result()
    t1 = time.time()
    print(f"Parallel fetch_all_rows took: {t1 - t0:.2f} seconds. Active: {len(active)}, Shelters: {len(shelters)}, Personas: {len(personas)}, Facts: {len(facts)}")

test_sequential()
test_parallel()
