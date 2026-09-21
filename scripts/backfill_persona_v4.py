#!/usr/bin/env python3
"""
Backfill script for Persona V4 fingerprints.

Usage:
    python -m scripts.backfill_persona_v4 --dry-run --limit 5
    python -m scripts.backfill_persona_v4 --animal-id MCACC-5157336
    python -m scripts.backfill_persona_v4 --only-missing-v4 --limit 50

Uses the same centralized helpers as the scheduled job and admin route
to ensure identical DB row shapes.
"""

import os
import sys
import json
import time
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("barkbot.backfill_v4")

# Ensure api/ is importable
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
api_dir = os.path.join(project_root, "api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    parser = argparse.ArgumentParser(description="Backfill Persona V4 fingerprints")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without modifying DB")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N dogs")
    parser.add_argument("--animal-id", type=str, default=None, help="Process a single dog by animal_id")
    parser.add_argument("--only-missing-v4", action="store_true", help="Only process dogs without a v4 fingerprint")
    parser.add_argument("--force", action="store_true", help="Overwrite existing v4 fingerprints")
    args = parser.parse_args()

    # Load env
    env_file = os.path.join(project_root, ".env.local")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    from openai import OpenAI
    from jobs.lib.db import get_supabase_client
    from pipeline.extract_fact_profiles import extract_fact_profile
    from pipeline.build_persona_profiles import build_persona_profile, enrich_persona_fingerprint
    from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt
    from pipeline.persona_helpers import persona_profile_to_db_row, build_render_context, prompt_record_to_db_row

    sb = get_supabase_client()
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Fetch archetypes
    archetypes = sb.table("persona_archetypes").select("*").eq("active", True).execute().data

    # Determine target dogs
    if args.animal_id:
        target_ids = [args.animal_id]
    else:
        # Fetch all dogs with existing persona profiles
        persona_data = []
        offset = 0
        while True:
            res = sb.table("animal_persona_profiles").select("animal_id, schema_version, persona_fingerprint_jsonb").range(offset, offset + 999).execute()
            persona_data.extend(res.data)
            if len(res.data) < 1000:
                break
            offset += 1000

        target_ids = []
        for row in persona_data:
            aid = row["animal_id"]
            if args.only_missing_v4:
                sv = row.get("schema_version", "persona_v3")
                fp = row.get("persona_fingerprint_jsonb", {})
                if sv == "persona_v4" and fp and not args.force:
                    continue
            target_ids.append(aid)

    if args.limit:
        target_ids = target_ids[:args.limit]

    logger.info(f"Target dogs: {len(target_ids)} | dry_run={args.dry_run} | force={args.force}")

    # Counters
    counts = {
        "selected": 0, "enriched": 0, "validated": 0,
        "retried": 0, "failed": 0, "rendered": 0, "persisted": 0, "skipped": 0,
    }

    for aid in target_ids:
        logger.info(f"Processing {aid}...")

        try:
            # Fetch the animal record
            animal_res = sb.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
            if not animal_res.data:
                logger.warning(f"  No animal record for {aid}, skipping")
                counts["skipped"] += 1
                continue

            animal_record = animal_res.data[0]
            record_hash = animal_record.get("record_hash", "none")

            # Fetch existing fact profile
            fact_res = sb.table("animal_fact_profiles").select("*").eq("animal_id", aid).limit(1).execute()
            if not fact_res.data:
                logger.warning(f"  No fact profile for {aid}, skipping")
                counts["skipped"] += 1
                continue

            fact_profile = fact_res.data[0]
            fact_profile["full_bio"] = animal_record.get("bio", "")

            # Fetch existing persona profile for archetype info
            persona_res = sb.table("animal_persona_profiles").select("*").eq("animal_id", aid).limit(1).execute()

            if persona_res.data:
                # Use existing archetype — don't re-select
                existing_persona = persona_res.data[0]
                archetype_key = existing_persona.get("primary_archetype_key")
                chosen_arch = next((a for a in archetypes if a["archetype_key"] == archetype_key), None)

                persona_profile = {
                    "animal_id": aid,
                    "primary_archetype_key": archetype_key,
                    "selection_reasoning": existing_persona.get("selection_reasoning", ""),
                    "characters": chosen_arch["characters"] if chosen_arch else "",
                    "linguistic_style": chosen_arch["linguistic_style"] if chosen_arch else "",
                    "_archetype_name": chosen_arch["name"] if chosen_arch else "",
                    "_archetype_evidence_criteria": chosen_arch["evidence_criteria"] if chosen_arch else "",
                }
                counts["selected"] += 1
            else:
                # Need to select archetype first
                persona_profile = build_persona_profile(openai_client, fact_profile, archetypes)
                counts["selected"] += 1

            # Enrich fingerprint
            if args.dry_run:
                logger.info(f"  [DRY RUN] Would enrich fingerprint for {aid} (archetype: {persona_profile.get('primary_archetype_key')})")
                counts["enriched"] += 1
                continue

            fingerprint = enrich_persona_fingerprint(openai_client, fact_profile, persona_profile)
            if not fingerprint:
                logger.error(f"  Enrichment failed for {aid}")
                counts["failed"] += 1
                continue

            fingerprint_dict = fingerprint.model_dump()
            counts["enriched"] += 1
            counts["validated"] += 1

            persona_profile["enrichment_model"] = "gpt-4o-mini"
            persona_profile["enrichment_params_jsonb"] = {"temperature": 1.0}

            # Persist persona
            db_persona = persona_profile_to_db_row(persona_profile, record_hash, fingerprint_dict)
            sb.table("animal_persona_profiles").upsert(db_persona).execute()

            # Render and persist system prompt
            system_prompt = render_system_prompt(fact_profile, persona_profile, fingerprint_dict)
            validation = validate_system_prompt(system_prompt)
            render_context = build_render_context(fact_profile, persona_profile, fingerprint_dict)

            prompt_record = prompt_record_to_db_row(
                animal_id=aid,
                system_prompt=system_prompt,
                source_record_hash=record_hash,
                render_context=render_context,
                validation=validation,
                prompt_version="v4",
            )
            sb.table("system_prompts_v2").upsert(prompt_record).execute()

            counts["rendered"] += 1
            counts["persisted"] += 1
            logger.info(f"  ✅ {aid} — v4 fingerprint + prompt persisted")

        except Exception as e:
            logger.error(f"  ❌ Failed for {aid}: {e}")
            counts["failed"] += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  Selected:  {counts['selected']}")
    logger.info(f"  Enriched:  {counts['enriched']}")
    logger.info(f"  Validated: {counts['validated']}")
    logger.info(f"  Rendered:  {counts['rendered']}")
    logger.info(f"  Persisted: {counts['persisted']}")
    logger.info(f"  Failed:    {counts['failed']}")
    logger.info(f"  Skipped:   {counts['skipped']}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
