#!/usr/bin/env python3
"""
One-time cleanup script to delete records from system_prompts_v2, animal_persona_profiles,
and animal_fact_profiles for dogs that do not meet prompt generation eligibility requirements:
- Dog must be active (present in active_dogs table).
- For NYCACC, MUDDYPAWS, and PIMA (PACC): Requires LENGTH(description) >= 1500 OR LENGTH(bio) >= 1500.
- For HSSA: Requires LENGTH(description) >= 500 OR LENGTH(bio) >= 500.
- Others: Fallback default of > 400.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from supabase import create_client

def get_supabase_client():
    env_local = Path(__file__).resolve().parent.parent / ".env.local"
    env_dev = Path(__file__).resolve().parent.parent / ".env.development.local"
    for env_file in (env_local, env_dev):
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ[k] = v.strip().strip('"').strip("'")
                        
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc

def is_eligible(bio: str | None, desc: str | None, shelter_id: str | None) -> bool:
    if not shelter_id:
        return False
    
    s_id_upper = shelter_id.upper()
    bio_len = len(bio or "")
    desc_len = len(desc or "")
    
    if s_id_upper in ("NYCACC", "MUDDYPAWS", "PIMA"):
        return bio_len >= 1500 or desc_len >= 1500
    elif s_id_upper == "HSSA":
        return bio_len >= 500 or desc_len >= 500
    else:
        return max(bio_len, desc_len) > 400

def main():
    print("Connecting to Supabase...")
    try:
        client = get_supabase_client()
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print("Fetching active_dogs...")
    active_res = client.table("active_dogs").select("animal_id, shelter_id").execute()
    active_dogs_map = {row["animal_id"]: row.get("shelter_id") for row in active_res.data}
    print(f"Found {len(active_dogs_map)} active dogs.")

    print("Fetching animals (bios and descriptions)...")
    animals_res = client.table("animals").select("animal_id, bio, description").execute()
    animals_map = {row["animal_id"]: row for row in animals_res.data}
    print(f"Found {len(animals_map)} registered animals.")

    # Get all animal_ids present in target tables
    print("Scanning system_prompts_v2, animal_persona_profiles, animal_fact_profiles...")
    
    prompts_res = client.table("system_prompts_v2").select("animal_id").execute()
    prompt_ids = {row["animal_id"] for row in prompts_res.data}
    
    personas_res = client.table("animal_persona_profiles").select("animal_id").execute()
    persona_ids = {row["animal_id"] for row in personas_res.data}
    
    facts_res = client.table("animal_fact_profiles").select("animal_id").execute()
    fact_ids = {row["animal_id"] for row in facts_res.data}

    all_target_ids = prompt_ids.union(persona_ids).union(fact_ids)
    print(f"Found {len(all_target_ids)} unique animal_ids with prompts, personas, or fact profiles.")

    ineligible_ids = []
    for aid in all_target_ids:
        # Check active status & eligibility
        shelter_id = active_dogs_map.get(aid)
        animal_row = animals_map.get(aid) or {}
        bio = animal_row.get("bio")
        desc = animal_row.get("description")
        
        if not is_eligible(bio, desc, shelter_id):
            ineligible_ids.append(aid)

    if not ineligible_ids:
        print("No ineligible prompts/profiles found. Database is already clean!")
        return 0

    print(f"Found {len(ineligible_ids)} ineligible dogs to clear from prompt tables.")
    
    # Let's show a few examples of what we're deleting for verification
    print("Examples of ineligible dogs being cleared:")
    for aid in ineligible_ids[:5]:
        shelter_id = active_dogs_map.get(aid)
        animal_row = animals_map.get(aid) or {}
        bio_len = len(animal_row.get("bio") or "")
        desc_len = len(animal_row.get("description") or "")
        print(f" - {aid}: shelter={shelter_id}, bio_len={bio_len}, desc_len={desc_len}")

    # Perform the deletion in chunks of 100
    CHUNK_SIZE = 100
    total_prompts_deleted = 0
    total_personas_deleted = 0
    total_facts_deleted = 0

    for i in range(0, len(ineligible_ids), CHUNK_SIZE):
        chunk = ineligible_ids[i:i+CHUNK_SIZE]
        
        # Check counts before delete (for logging)
        chunk_set = set(chunk)
        prompts_in_chunk = len(chunk_set.intersection(prompt_ids))
        personas_in_chunk = len(chunk_set.intersection(persona_ids))
        facts_in_chunk = len(chunk_set.intersection(fact_ids))

        client.table("system_prompts_v2").delete().in_("animal_id", chunk).execute()
        client.table("animal_persona_profiles").delete().in_("animal_id", chunk).execute()
        client.table("animal_fact_profiles").delete().in_("animal_id", chunk).execute()

        total_prompts_deleted += prompts_in_chunk
        total_personas_deleted += personas_in_chunk
        total_facts_deleted += facts_in_chunk

    print("Cleanup Completed Successfully!")
    print(f"Total system prompts deleted: {total_prompts_deleted}")
    print(f"Total persona profiles deleted: {total_personas_deleted}")
    print(f"Total fact profiles deleted: {total_facts_deleted}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
