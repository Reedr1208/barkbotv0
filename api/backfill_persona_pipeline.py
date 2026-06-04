import os
import sys
import json
import logging
from supabase import create_client
from openai import OpenAI

from pipeline.extract_fact_profiles import extract_fact_profile
from pipeline.build_persona_profiles import build_persona_profile
from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
    # Load env variables locally if needed
    env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val

    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        logging.error("Missing Supabase environment variables.")
        sys.exit(1)
        
    sb_client = create_client(supabase_url, supabase_key)
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Fetch active dogs from active_dogs
    active_res = sb_client.table("active_dogs").select("animal_id, shelter_id").execute()
    active_dogs_map = {row["animal_id"]: row.get("shelter_id") for row in active_res.data}

    # Fetch dogs to backfill
    res = sb_client.table("animals").select("*").execute()
    
    # Fetch existing prompts to avoid re-running all
    prompts_res = sb_client.table("system_prompts_v2").select("animal_id").execute()
    existing_prompt_ids = {row["animal_id"] for row in prompts_res.data}
    
    dogs = []
    for row in res.data:
        aid = row["animal_id"]
        bio = row.get("bio") or ""
        desc = row.get("description") or ""
        shelter_id = active_dogs_map.get(aid)
        
        if shelter_id:
            # All dogs must have at least 400 characters of text
            max_len = max(len(bio), len(desc))
            if max_len <= 400:
                continue
                
            # PIMA requires bio > 1000.
            if shelter_id == "PIMA" and len(bio) <= 1000:
                continue
            
            # Skip dogs that already have prompts
            if aid in existing_prompt_ids:
                continue
                
            dogs.append(row)

    if not dogs:
        logging.info("No eligible dogs found in the database.")
        return

    # Fetch catalogs
    archetypes_res = sb_client.table("persona_archetypes").select("*").eq("active", True).execute()
    archetypes = archetypes_res.data

    # Fetch current distribution to prevent skewed archetype assignment
    dist_res = sb_client.table("animal_persona_profiles").select("primary_archetype_key").execute()
    distribution = {}
    for row in dist_res.data:
        k = row.get("primary_archetype_key")
        if k:
            distribution[k] = distribution.get(k, 0) + 1

    for dog in dogs:
        animal_id = dog["animal_id"]
        record_hash = dog.get("record_hash", "none")
        logging.info(f"Processing {animal_id}...")

        try:
            # 1. Fact Extraction
            fact_res = sb_client.table("animal_fact_profiles").select("*").eq("animal_id", animal_id).limit(1).execute()
            if fact_res.data:
                fact_profile = fact_res.data[0]
                logging.info(f"Using existing fact profile for {animal_id}.")
            else:
                logging.info(f"Extracting fact profile for {animal_id}...")
                fact_profile_obj = extract_fact_profile(openai_client, dog)
                fact_profile = fact_profile_obj.model_dump()
                fact_profile["animal_id"] = animal_id
                fact_profile["source_record_hash"] = record_hash
                fact_profile["schema_version"] = "fact_v1"
                fact_profile["extraction_model"] = "gpt-4o-mini"
                fact_profile["extraction_params_jsonb"] = {"temperature": 0.2}
                
                # Upsert
                sb_client.table("animal_fact_profiles").upsert(fact_profile).execute()

            # Inject full bio and description for persona building and prompt rendering
            fact_profile["full_bio"] = dog.get("bio", "")
            fact_profile["full_description"] = dog.get("description", "")

            # 2. Persona Scoring
            persona_profile = build_persona_profile(openai_client, fact_profile, archetypes, distribution)
            
            # Update local distribution so it balances dynamically during the run
            assigned_key = persona_profile.get("primary_archetype_key")
            if assigned_key:
                distribution[assigned_key] = distribution.get(assigned_key, 0) + 1
            persona_profile["source_record_hash"] = record_hash
            
            db_persona = {
                "animal_id": persona_profile.get("animal_id"),
                "source_record_hash": persona_profile.get("source_record_hash"),
                "primary_archetype_key": persona_profile.get("primary_archetype_key"),
                "selection_reasoning": persona_profile.get("selection_reasoning"),
            }
            sb_client.table("animal_persona_profiles").upsert(db_persona).execute()

            # 3. Prompt Rendering
            system_prompt = render_system_prompt(fact_profile, persona_profile)
            validation = validate_system_prompt(system_prompt)
            
            render_context = {
                "fact_profile_used": True,
                "persona_profile_used": True,
                "archetype": persona_profile.get("primary_archetype_key")
            }

            prompt_record = {
                "animal_id": persona_profile.get("animal_id"),
                "prompt_version": "v3",
                "source_record_hash": record_hash,
                "system_prompt": system_prompt,
                "render_context_jsonb": render_context,
                "validation_results_jsonb": validation,
                "is_active": True
            }

            sb_client.table("system_prompts_v2").upsert(prompt_record).execute()
            logging.info(f"Successfully processed {animal_id}")

        except Exception as e:
            logging.error(f"Failed to process {animal_id}: {e}")

if __name__ == "__main__":
    main()
