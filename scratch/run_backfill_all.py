import json
import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List
from pathlib import Path
from pydantic import BaseModel, Field
from openai import OpenAI
from supabase import create_client

# Ensure the pipeline modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'api')))

# Force load .env.development.local if present
env_local = Path(__file__).resolve().parent.parent / ".env.development.local"
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
    start_time = time.time()
    logging.info("Starting RESUMED manual backfill job...")

    try:
        supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        sb_client = create_client(supabase_url, supabase_key)
        
        # Configure OpenAI with a 60 second timeout to prevent hanging
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=60.0, max_retries=3)

        archetypes_res = sb_client.table("persona_archetypes").select("*").eq("active", True).execute()
        archetypes = archetypes_res.data

        active_res = sb_client.table("active_dogs").select("animal_id, shelter_id").execute()
        active_dogs_map = {row["animal_id"]: row.get("shelter_id") for row in active_res.data}
        
        if not active_dogs_map:
            logging.info("No active dogs found in active_dogs.")
            return

        animals_res = sb_client.table("animals").select("animal_id, bio").execute()
        
        eligible_animal_ids = []
        for row in animals_res.data:
            aid = row["animal_id"]
            bio = row.get("bio") or ""
            desc = row.get("bio") or ""
            shelter_id = active_dogs_map.get(aid)
            
            if shelter_id:
                s_id_upper = shelter_id.upper()
                bio_len = len(bio)
                desc_len = len(desc)
                if s_id_upper in ("NYCACC", "MUDDYPAWS", "PIMA"):
                    if bio_len < 1500 and desc_len < 1500:
                        continue
                elif s_id_upper == "HSSA":
                    if bio_len < 500 and desc_len < 500:
                        continue
                else:
                    if max(bio_len, desc_len) <= 400:
                        continue
                        
                eligible_animal_ids.append(aid)

        # Check existing prompts updated today to avoid reprocessing
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
        prompts_res = sb_client.table("system_prompts_v2").select("animal_id, updated_at").execute()
        
        existing_updated = set()
        for row in prompts_res.data:
            aid = row["animal_id"]
            dt_str = row["updated_at"]
            if dt_str:
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                try:
                    updated_at = datetime.fromisoformat(dt_str)
                    if updated_at > two_hours_ago:
                        existing_updated.add(aid)
                except ValueError:
                    pass

        target_ids = [aid for aid in eligible_animal_ids if aid not in existing_updated]
        logging.info(f"Selected {len(target_ids)} dogs requiring prompt generation (RESUMED RUN).")

        processed_count = 0
        from pipeline.extract_fact_profiles import extract_fact_profile
        from pipeline.build_persona_profiles import build_persona_profile
        from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

        dist_res = sb_client.table("animal_persona_profiles").select("primary_archetype_key").execute()
        distribution = {}
        for row in dist_res.data:
            k = row.get("primary_archetype_key")
            if k:
                distribution[k] = distribution.get(k, 0) + 1

        for aid in target_ids:
            logging.info(f"Processing animal_id: {aid} ({processed_count + 1}/{len(target_ids)})")
            
            animal_record_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
            if not animal_record_res.data:
                continue
                
            animal_record = animal_record_res.data[0]
            record_hash = animal_record.get("record_hash", "none")
            updated_at = animal_record.get("updated_at")
            adoption_url = animal_record.get("shelter_profile_url")
            shelter_name = animal_record.get("shelter_name")
            
            for key in ["id", "record_hash", "created_at", "updated_at", "last_scrape_run_id"]:
                animal_record.pop(key, None)

            try:
                fact_profile_obj = extract_fact_profile(openai_client, animal_record)
                fact_profile = fact_profile_obj.model_dump()
                fact_profile["animal_id"] = aid
                fact_profile["source_record_hash"] = record_hash
                fact_profile["schema_version"] = "fact_v1"
                fact_profile["extraction_model"] = "gpt-5.4-mini"
                fact_profile["extraction_params_jsonb"] = {"temperature": 0.2}
                fact_profile["info_refreshed_at"] = updated_at
                fact_profile["adoption_url"] = adoption_url
                fact_profile["shelter_name"] = shelter_name
                sb_client.table("animal_fact_profiles").upsert(fact_profile).execute()

                fact_profile["full_bio"] = animal_record.get("bio", "")

                persona_profile = build_persona_profile(openai_client, fact_profile, archetypes, distribution)
                
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

                system_prompt = render_system_prompt(fact_profile, persona_profile)
                validation = validate_system_prompt(system_prompt)
                
                render_context = {
                    "fact_profile_used": True,
                    "persona_profile_used": True,
                    "archetype": persona_profile.get("primary_archetype_key")
                }

                prompt_record = {
                    "animal_id": aid,
                    "prompt_version": "v3",
                    "source_record_hash": record_hash,
                    "system_prompt": system_prompt,
                    "render_context_jsonb": render_context,
                    "validation_results_jsonb": validation,
                    "is_active": True
                }

                sb_client.table("system_prompts_v2").upsert(prompt_record).execute()
                
                processed_count += 1
                
            except Exception as gen_exc:
                logging.error(f"Failed to generate/upsert for {aid}: {gen_exc}")

        elapsed = time.time() - start_time
        logging.info(f"Job completed. Processed {processed_count} prompts in {elapsed:.2f}s.")
        
    except Exception as e:
        logging.exception("An unexpected error occurred in manual backfill.")

if __name__ == "__main__":
    main()
