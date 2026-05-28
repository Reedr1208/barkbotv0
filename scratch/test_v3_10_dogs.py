import os
import sys
import json
import logging
from supabase import create_client
from openai import OpenAI
import random

from api.pipeline.extract_fact_profiles import extract_fact_profile
from api.pipeline.build_persona_profiles import build_persona_profile
from api.pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
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

    # Fetch active dogs from pima_all_dogs
    pima_res = sb_client.table("pima_all_dogs").select("animal_id").execute()
    active_ids = {row["animal_id"] for row in pima_res.data}

    if not active_ids:
        logging.info("No active dogs found.")
        return

    # Fetch all animals to check bio length
    animals_res = sb_client.table("animals").select("animal_id, bio").execute()
    eligible_animal_ids = set()
    for row in animals_res.data:
        aid = row["animal_id"]
        bio = row.get("bio") or ""
        if aid in active_ids and len(bio) > 1000:
            eligible_animal_ids.add(aid)

    test_ids = [
        "A881677", "A887098", "A892175", "A889730", "A894897",
        "A900036", "A890087", "A888740", "A896162", "A861842"
    ]
    
    logging.info(f"Re-running prompt generation for 10 specific dogs: {test_ids}")

    # Fetch catalogs
    archetypes_res = sb_client.table("persona_archetypes").select("*").eq("active", True).execute()
    archetypes = archetypes_res.data

    processed = []
    
    for aid in test_ids:
        logging.info(f"Processing {aid}...")

        # Fetch full animal record
        animal_record_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
        if not animal_record_res.data:
            continue
        dog = animal_record_res.data[0]
        record_hash = dog.get("record_hash", "none")
        
        # Strip developer fields
        internal_keys = ["id", "record_hash", "qa_status", "qa_notes", "created_at", "updated_at", "last_scrape_run_id", "data_updated"]
        for key in internal_keys:
            dog.pop(key, None)

        try:
            # 1. Fact Extraction
            fact_profile_obj = extract_fact_profile(openai_client, dog)
            fact_profile = fact_profile_obj.model_dump()
            fact_profile["animal_id"] = aid
            fact_profile["source_record_hash"] = record_hash
            fact_profile["schema_version"] = "fact_v1"
            fact_profile["extraction_model"] = "gpt-4o-mini"
            fact_profile["extraction_params_jsonb"] = {"temperature": 0.2}
            
            sb_client.table("animal_fact_profiles").upsert(fact_profile).execute()

            # 2. Persona Scoring
            persona_profile = build_persona_profile(openai_client, fact_profile, archetypes)
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
                "animal_id": aid,
                "prompt_version": "v3_test",
                "source_record_hash": record_hash,
                "system_prompt": system_prompt,
                "render_context_jsonb": render_context,
                "validation_results_jsonb": validation,
                "is_active": True
            }

            sb_client.table("system_prompts_v2").upsert(prompt_record).execute()
            logging.info(f"Successfully processed {aid} -> Assigned {persona_profile.get('primary_archetype_key')}")
            processed.append(aid)

        except Exception as e:
            logging.error(f"Failed to process {aid}: {e}")

    print("\n--- TEST COMPLETE ---")
    print(f"Processed Animal IDs: {', '.join(processed)}")

if __name__ == "__main__":
    main()
