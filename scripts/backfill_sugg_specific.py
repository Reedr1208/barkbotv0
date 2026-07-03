"""
Backfill: Generate sugg_specific for 10 dogs
----------------------------------------------
Picks 10 dogs that have existing animal_fact_profiles but no sugg_specific,
re-runs the fact extraction pipeline to generate profile-specific suggested prompts,
and upserts the result back to animal_fact_profiles.
"""

import os
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Ensure pipeline modules can be imported (from api/ directory)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'api'))

# Load env
env_file = Path(__file__).resolve().parent.parent / ".env.development.local"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

from supabase import create_client
from openai import OpenAI
from pipeline.extract_fact_profiles import extract_fact_profile

supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not supabase_url or not supabase_key:
    logging.error("Missing Supabase environment variables.")
    sys.exit(1)

sb = create_client(supabase_url, supabase_key)
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Find dogs with existing fact profiles but no sugg_specific
logging.info("Finding dogs that need sugg_specific backfill...")

# Fetch animal_fact_profiles that have no sugg_specific (null)
res = sb.table("animal_fact_profiles").select("animal_id").is_("sugg_specific", "null").limit(10).execute()

if not res.data:
    logging.info("No dogs found needing sugg_specific backfill.")
    sys.exit(0)

target_ids = [row["animal_id"] for row in res.data]
logging.info(f"Found {len(target_ids)} dogs to backfill: {target_ids}")

backfilled_ids = []

for aid in target_ids:
    logging.info(f"Processing {aid}...")
    
    try:
        # Fetch the full animal record
        animal_res = sb.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
        if not animal_res.data:
            logging.warning(f"  No animal record found for {aid}, skipping.")
            continue
        
        animal_record = animal_res.data[0]
        record_hash = animal_record.get("record_hash", "none")
        updated_at = animal_record.get("updated_at")
        adoption_url = animal_record.get("shelter_profile_url")
        shelter_name = animal_record.get("shelter_name")
        
        # Strip developer fields before sending to LLM
        internal_keys = ["id", "record_hash", "created_at", "updated_at", "last_scrape_run_id"]
        for key in internal_keys:
            animal_record.pop(key, None)
        
        # Run fact extraction (this now includes sugg_specific)
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
        
        # Upsert the full fact profile (includes sugg_specific)
        sb.table("animal_fact_profiles").upsert(fact_profile).execute()
        
        sugg_count = len(fact_profile.get("sugg_specific", []))
        logging.info(f"  ✓ {aid} — generated {sugg_count} profile-specific prompts:")
        for sp in fact_profile.get("sugg_specific", []):
            logging.info(f"      • {sp}")
        
        backfilled_ids.append(aid)
        
    except Exception as e:
        logging.error(f"  ✗ Failed for {aid}: {e}")

logging.info(f"\n{'='*60}")
logging.info(f"Backfill complete! {len(backfilled_ids)}/{len(target_ids)} dogs processed.")
logging.info(f"Backfilled animal IDs:")
for aid in backfilled_ids:
    logging.info(f"  - {aid}")
logging.info(f"{'='*60}")
