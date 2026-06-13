#!/usr/bin/env python3
"""
Cron job to delete inactive dog records from relevant tables in the Supabase database.
An inactive dog is defined as a dog that exists in the `animals` table but is NOT
present in the `active_dogs` table.

Safety features:
- Group and process deletion one batch at a time for each shelter_id.
- If a shelter has fewer than 5 active dogs in `active_dogs`, skip cleaning up that shelter
  for this run (prevents mass deletion of a shelter's history if its scraper is in the
  middle of an active dogs overwrite).
- Delete associated saved images from the Supabase storage bucket.
- Explicitly delete from system_prompts_v2, animal_persona_profiles, and animal_fact_profiles.
- Deletions from `animals` will cascade to saved_dogs, chat_conversations, chat_messages,
  animal_versions, and animal_change_events.
- Runs every 4 hours.
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SAFETY_THRESHOLD = 5
def get_shelter_id_for_animal(animal_id: str) -> str:
    if animal_id.startswith("NYCACC-"):
        return "NYCACC"
    elif animal_id.startswith("HSSA-"):
        return "HSSA"
    elif animal_id.startswith("PACC-") or animal_id.startswith("PIMA-"):
        return "PACC"
    elif animal_id.startswith("MP-") or animal_id.isdigit():
        return "MP"
    elif animal_id.startswith("PAWSCH-"):
        return "PAWSCH"
    elif animal_id.startswith("WWLA-"):
        return "WWLA"
    elif animal_id.startswith("HHS-"):
        return "HHS"
    else:
        return "UNKNOWN"

def get_supabase_client():
    from pathlib import Path
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

def begin_run(client, source_count: int) -> int:
    payload = {
        "triggered_by": "cron_cleanup_inactive_dogs",
        "source_count": source_count,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }
    row = client.table("scrape_runs").insert(payload).execute().data[0]
    return row["id"]

def finish_run(client, run_id: int, status: str, processed: int, deleted: int, errors: int, notes: str) -> None:
    payload = {
        "status": status,
        "processed_count": processed,
        "notes": notes,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("scrape_runs").update(payload).eq("id", run_id).execute()

def main() -> int:
    logging.info("Starting inactive dogs database cleanup job...")
    try:
        client = get_supabase_client()
    except Exception as e:
        logging.error(f"Failed to initialize Supabase client: {e}")
        return 1

    bucket_name = os.getenv("SUPABASE_BUCKET", "animal-images")

    # Fetch all currently active dogs (paginated to bypass 1000-row limit)
    active_data = []
    start_row = 0
    while True:
        try:
            active_res = client.table("active_dogs").select("animal_id, shelter_id").range(start_row, start_row + 999).execute()
        except Exception as e:
            logging.error(f"Failed to fetch active_dogs: {e}")
            return 1
            
        if not active_res.data:
            break
            
        active_data.extend(active_res.data)
        if len(active_res.data) < 1000:
            break
            
        start_row += 1000

    active_by_shelter = {}
    for row in active_data:
        sid = row.get("shelter_id")
        aid = row.get("animal_id")
        if sid and aid:
            active_by_shelter.setdefault(sid, set()).add(aid)

    # Fetch all animals registered in animals database
    # Fetch in chunks to bypass Supabase's default 1000-row limit
    db_by_shelter = {}
    start_row = 0
    animals_count = 0
    while True:
        try:
            animals_res = client.table("animals").select("animal_id, image_file, shelter_id").range(start_row, start_row + 999).execute()
        except Exception as e:
            logging.error(f"Failed to fetch animals: {e}")
            return 1
            
        if not animals_res.data:
            break
            
        animals_count += len(animals_res.data)
        
        for row in animals_res.data:
            aid = row.get("animal_id")
            image_file = row.get("image_file")
            sid = row.get("shelter_id")
            
            if not sid and aid:
                sid = get_shelter_id_for_animal(aid)
                
            if aid and sid and sid != "UNKNOWN":
                db_by_shelter.setdefault(sid, []).append((aid, image_file))
                
        if len(animals_res.data) < 1000:
            break
        start_row += 1000

    # Log execution start
    run_id = begin_run(client, animals_count)

    total_deleted = 0
    total_errors = 0
    shelter_logs = []

    recognized_shelters = set(active_by_shelter.keys()).union(set(db_by_shelter.keys()))

    for shelter in recognized_shelters:
        active_set = active_by_shelter.get(shelter, set())
        active_count = len(active_set)

        if active_count < SAFETY_THRESHOLD:
            log_msg = f"Skipped {shelter}: active count ({active_count}) is below safety threshold ({SAFETY_THRESHOLD})."
            logging.info(log_msg)
            shelter_logs.append(log_msg)
            continue

        db_animals = db_by_shelter.get(shelter, [])
        inactive_animals = [item for item in db_animals if item[0] not in active_set]

        if not inactive_animals:
            log_msg = f"Shelter {shelter}: No inactive dogs found to delete (Active: {active_count}, DB: {len(db_animals)})."
            logging.info(log_msg)
            shelter_logs.append(log_msg)
            continue

        inactive_ids = [item[0] for item in inactive_animals]
        image_files = [item[1] for item in inactive_animals if item[1]]

        log_msg = f"Shelter {shelter}: Processing deletion of {len(inactive_ids)} inactive dogs (Active: {active_count}, DB: {len(db_animals)})."
        logging.info(log_msg)
        shelter_logs.append(log_msg)

        # 1. Delete associated images from Supabase Storage
        if image_files:
            try:
                # remove requires a list of file paths
                client.storage.from_(bucket_name).remove(image_files)
                logging.info(f"  Deleted {len(image_files)} image files from bucket '{bucket_name}' for {shelter}.")
            except Exception as e:
                logging.error(f"  Error deleting images for {shelter}: {e}")
                total_errors += 1

        # 2. Delete database records in chunks to prevent URL/payload size issues
        CHUNK_SIZE = 100
        for i in range(0, len(inactive_ids), CHUNK_SIZE):
            chunk = inactive_ids[i:i+CHUNK_SIZE]
            try:
                # Explicit delete from child/associated tables without cascade first
                client.table("system_prompts_v2").delete().in_("animal_id", chunk).execute()
                client.table("animal_persona_profiles").delete().in_("animal_id", chunk).execute()
                client.table("animal_fact_profiles").delete().in_("animal_id", chunk).execute()
                
                # Delete from core animals table (triggers cascade deletes for saved_dogs, chat_conversations, chat_messages, animal_versions, animal_change_events)
                client.table("animals").delete().in_("animal_id", chunk).execute()
                total_deleted += len(chunk)
            except Exception as e:
                logging.error(f"  Error deleting database records in chunk starting at index {i}: {e}")
                total_errors += 1

    final_notes = "; ".join(shelter_logs)
    status = "success" if total_errors == 0 else "partial_success"
    finish_run(client, run_id, status, len(animals_res.data), total_deleted, total_errors, final_notes)
    logging.info(f"Cleanup finished. Deleted {total_deleted} dogs. Errors: {total_errors}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
