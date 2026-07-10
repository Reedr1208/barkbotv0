"""
Generate prompts job — extracted from api/generate_prompts.py for serverful execution.

Runs the full pipeline (fact extraction → persona scoring → prompt rendering)
for all eligible dogs that need new or refreshed prompts. Called directly
by APScheduler — no HTTP handler, no subprocess.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

from openai import OpenAI
from pydantic import BaseModel, Field

from jobs.lib.db import get_supabase_client

logger = logging.getLogger("barkbot.jobs.generate_prompts")

# On Railway there's no Vercel 300s limit. Allow up to 15 minutes per run.
MAX_EXECUTION_TIME = 900


def run():
    """Execute the generate_prompts pipeline. Called by APScheduler."""
    start_time = time.time()
    logger.info("Starting generate_prompts job...")

    try:
        sb_client = get_supabase_client()
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Fetch catalogs
        archetypes_res = sb_client.table("persona_archetypes").select("*").eq("active", True).execute()
        archetypes = archetypes_res.data

        # 1. Fetch active dogs (paginated)
        active_data = []
        start_row = 0
        while True:
            res = sb_client.table("active_dogs").select("animal_id, shelter_id").range(start_row, start_row + 999).execute()
            active_data.extend(res.data)
            if len(res.data) < 1000:
                break
            start_row += 1000

        active_dogs_map = {row["animal_id"]: row.get("shelter_id") for row in active_data}

        if not active_dogs_map:
            logger.info("No active dogs found in active_dogs.")
            return {"ok": True, "processed": 0, "message": "No active dogs found"}

        # 2. Fetch animals data in chunks
        active_ids = list(active_dogs_map.keys())
        animals_data = []
        for i in range(0, len(active_ids), 100):
            chunk = active_ids[i:i+100]
            res = sb_client.table("animals").select("animal_id, bio").in_("animal_id", chunk).execute()
            animals_data.extend(res.data)

        eligible_animal_ids = []
        for row in animals_data:
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
                elif s_id_upper in ("HSSA", "AHSCN"):
                    if bio_len < 500 and desc_len < 500:
                        continue
                elif s_id_upper == "PAWSCH":
                    if bio_len < 1200 and desc_len < 1200:
                        continue
                elif s_id_upper in ("WWLA", "HHS", "PHP", "SAPA"):
                    if bio_len < 1000 and desc_len < 1000:
                        continue
                elif s_id_upper in ("RCHS", "DPA", "NHS", "EHR", "MV", "RDR"):
                    if bio_len < 500 and desc_len < 500:
                        continue
                elif s_id_upper == "MCACC":
                    if bio_len < 6000 and desc_len < 6000:
                        continue
                else:
                    if max(bio_len, desc_len) <= 400:
                        continue

                eligible_animal_ids.append(aid)

        if not eligible_animal_ids:
            logger.info("No active eligible dogs found.")
            return {"ok": True, "processed": 0, "message": "No eligible dogs found"}

        # 3. Fetch existing prompts in chunks
        prompts_data = []
        for i in range(0, len(eligible_animal_ids), 100):
            chunk = eligible_animal_ids[i:i+100]
            res = sb_client.table("system_prompts_v2").select("animal_id, updated_at").in_("animal_id", chunk).execute()
            prompts_data.extend(res.data)

        existing_prompts = {row["animal_id"]: row["updated_at"] for row in prompts_data}

        # 4. Filter and sort targets
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        targets = []
        for aid in eligible_animal_ids:
            if aid not in existing_prompts:
                targets.append((aid, datetime.min.replace(tzinfo=timezone.utc)))
            else:
                dt_str = existing_prompts[aid]
                try:
                    if dt_str.endswith("Z"):
                        dt_str = dt_str[:-1] + "+00:00"
                    updated_at = datetime.fromisoformat(dt_str)
                except ValueError:
                    updated_at = datetime.min.replace(tzinfo=timezone.utc)
                if updated_at < three_days_ago:
                    targets.append((aid, updated_at))

        # Priority 2: active dogs with stale prompts that are no longer eligible
        eligible_set = set(eligible_animal_ids)
        all_active_ids = list(active_dogs_map.keys())
        stale_prompts_data = []
        for i in range(0, len(all_active_ids), 100):
            chunk = all_active_ids[i:i+100]
            res = sb_client.table("system_prompts_v2").select("animal_id, updated_at").in_("animal_id", chunk).execute()
            stale_prompts_data.extend(res.data)

        for row in stale_prompts_data:
            aid = row["animal_id"]
            if aid in eligible_set:
                continue
            dt_str = row["updated_at"]
            try:
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                updated_at = datetime.fromisoformat(dt_str)
            except ValueError:
                updated_at = datetime.min.replace(tzinfo=timezone.utc)
            if updated_at < three_days_ago:
                targets.append((aid, updated_at))

        targets.sort(key=lambda x: x[1])
        target_ids = [t[0] for t in targets]
        logger.info(f"Found {len(target_ids)} dogs requiring prompt generation.")

        processed_count = 0

        # 5. Process loop — import pipeline modules
        # The pipeline modules live in api/pipeline/ — ensure they're importable
        api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api")
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)

        from pipeline.extract_fact_profiles import extract_fact_profile
        from pipeline.build_persona_profiles import build_persona_profile
        from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

        # Fetch current distribution
        dist_data = []
        dist_offset = 0
        while True:
            dist_res = sb_client.table("animal_persona_profiles").select("primary_archetype_key").range(dist_offset, dist_offset + 999).execute()
            dist_data.extend(dist_res.data)
            if len(dist_res.data) < 1000:
                break
            dist_offset += 1000
        distribution = {}
        for row in dist_data:
            k = row.get("primary_archetype_key")
            if k:
                distribution[k] = distribution.get(k, 0) + 1

        for aid in target_ids:
            if time.time() - start_time > MAX_EXECUTION_TIME:
                logger.info("Nearing execution time limit. Halting gracefully.")
                break

            logger.info(f"Processing animal_id: {aid}")

            animal_record_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
            if not animal_record_res.data:
                continue

            animal_record = animal_record_res.data[0]
            record_hash = animal_record.get("record_hash", "none")
            updated_at = animal_record.get("updated_at")
            adoption_url = animal_record.get("shelter_profile_url")
            shelter_name = animal_record.get("shelter_name")

            internal_keys = ["id", "record_hash", "created_at", "updated_at", "last_scrape_run_id"]
            for key in internal_keys:
                animal_record.pop(key, None)

            try:
                # 1. Fact Extraction
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

                # 2. Persona Scoring
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
                logger.error(f"Failed to generate/upsert for {aid}: {gen_exc}")

        elapsed = time.time() - start_time
        logger.info(f"Job completed. Processed {processed_count} prompts in {elapsed:.2f}s.")
        return {"ok": True, "processed": processed_count, "elapsed_seconds": elapsed}

    except Exception as e:
        logger.exception("An unexpected error occurred in generate_prompts.")
        return {"ok": False, "error": str(e)}
