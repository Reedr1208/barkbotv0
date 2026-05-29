import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List
from pathlib import Path
from pydantic import BaseModel, Field
from openai import OpenAI
from supabase import create_client
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        start_time = time.time()
        logging.info("Starting generate_prompts job...")

        # Time limit in seconds (170 seconds = 2m 50s) to comfortably avoid 3m Vercel limit
        MAX_EXECUTION_TIME = 180
        try:
            # Setup clients
            supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                raise RuntimeError("Missing Supabase environment variables.")
                
            sb_client = create_client(supabase_url, supabase_key)
            openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            # Fetch catalogs
            factors_res = sb_client.table("persona_factor_definitions").select("*").eq("active", True).execute()
            factors = factors_res.data
            
            archetypes_res = sb_client.table("persona_archetypes").select("*").eq("active", True).execute()
            archetypes = archetypes_res.data

            # 1. Fetch active dogs from pima_all_dogs
            pima_res = sb_client.table("pima_all_dogs").select("animal_id").execute()
            active_ids = {row["animal_id"] for row in pima_res.data}
            
            if not active_ids:
                logging.info("No active dogs found in pima_all_dogs.")
                self._send_response(200, {"message": "No active dogs found"})
                return

            # 2. Fetch all animals with bio length checking
            animals_res = sb_client.table("animals").select("animal_id, bio").execute()
            
            eligible_animal_ids = []
            for row in animals_res.data:
                aid = row["animal_id"]
                bio = row.get("bio") or ""
                if aid in active_ids and len(bio) > 1000:
                    eligible_animal_ids.append(aid)

            if not eligible_animal_ids:
                logging.info("No active dogs with bio length > 1000.")
                self._send_response(200, {"message": "No eligible dogs found"})
                return

            # 3. Fetch existing system_prompts
            prompts_res = sb_client.table("system_prompts_v2").select("animal_id, updated_at").execute()
            existing_prompts = {row["animal_id"]: row["updated_at"] for row in prompts_res.data}

            # 4. Filter and sort targets
            three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
            
            targets = []
            for aid in eligible_animal_ids:
                if aid not in existing_prompts:
                    # Missing (highest priority, assign oldest possible time)
                    targets.append((aid, datetime.min.replace(tzinfo=timezone.utc)))
                else:
                    # Parse updated_at
                    dt_str = existing_prompts[aid]
                    try:
                        if dt_str.endswith("Z"):
                            dt_str = dt_str[:-1] + "+00:00"
                        updated_at = datetime.fromisoformat(dt_str)
                    except ValueError:
                        updated_at = datetime.min.replace(tzinfo=timezone.utc)
                        
                    if updated_at < three_days_ago:
                        targets.append((aid, updated_at))

            # Sort by updated_at ascending (oldest/missing first)
            targets.sort(key=lambda x: x[1])
            
            target_ids = [t[0] for t in targets]
            logging.info(f"Found {len(target_ids)} dogs requiring prompt generation.")

            processed_count = 0
            
            # 5. Process loop
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            
            from pipeline.extract_fact_profiles import extract_fact_profile
            from pipeline.build_persona_profiles import build_persona_profile
            from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

            for aid in target_ids:
                if time.time() - start_time > MAX_EXECUTION_TIME:
                    logging.info("Nearing execution time limit. Halting gracefully.")
                    break
                    
                logging.info(f"Processing animal_id: {aid}")
                
                # Fetch full animal record
                animal_record_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
                if not animal_record_res.data:
                    continue
                    
                animal_record = animal_record_res.data[0]
                record_hash = animal_record.get("record_hash", "none")
                
                # Strip developer fields before sending to LLM
                internal_keys = ["id", "record_hash", "qa_status", "qa_notes", "created_at", "updated_at", "last_scrape_run_id", "data_updated"]
                for key in internal_keys:
                    animal_record.pop(key, None)

                # Generate prompt
                try:
                    # 1. Fact Extraction
                    fact_profile_obj = extract_fact_profile(openai_client, animal_record)
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
            self._send_response(200, {"ok": True, "processed": processed_count, "elapsed_seconds": elapsed})
            
        except Exception as e:
            logging.exception("An unexpected error occurred in generate_prompts.")
            self._send_response(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        self.do_GET()

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
