#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
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

def main():
    client = get_supabase_client()
    
    # Fetch all system prompts
    print("Fetching system_prompts_v2...")
    prompts_res = client.table("system_prompts_v2").select("animal_id, updated_at").execute()
    prompts = prompts_res.data
    print(f"Total prompts in DB: {len(prompts)}")
    
    # Fetch active dogs
    print("Fetching active_dogs...")
    active_res = client.table("active_dogs").select("animal_id, shelter_id").execute()
    active_dogs = {row["animal_id"]: row["shelter_id"] for row in active_res.data}
    print(f"Total active dogs: {len(active_dogs)}")
    
    # Fetch animals
    print("Fetching animals...")
    animals_res = client.table("animals").select("animal_id, bio, description").execute()
    animals = {row["animal_id"]: row for row in animals_res.data}
    
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    
    stale_records = []
    non_stale_records = []
    
    for row in prompts:
        aid = row["animal_id"]
        updated_at_str = row["updated_at"]
        if updated_at_str.endswith("Z"):
            updated_at_str = updated_at_str[:-1] + "+00:00"
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
        except ValueError:
            updated_at = datetime.min.replace(tzinfo=timezone.utc)
            
        if updated_at < three_days_ago:
            stale_records.append((aid, updated_at))
        else:
            non_stale_records.append((aid, updated_at))
            
    print(f"\nFound {len(stale_records)} stale prompts (updated > 3 days ago).")
    print(f"Found {len(non_stale_records)} fresh prompts (updated <= 3 days ago).")
    
    # Print the distribution of non-stale prompts
    print("\nFresh prompts updated_at times (newest first):")
    for aid, updated_at in sorted(non_stale_records, key=lambda x: x[1], reverse=True):
        print(f" - {aid}: {updated_at}")
        
    print("\nDetailed analysis of first 20 stale prompts:")

    for aid, updated_at in sorted(stale_records, key=lambda x: x[1])[:20]:
        shelter_id = active_dogs.get(aid)
        is_active = aid in active_dogs
        animal = animals.get(aid)
        bio_len = len(animal.get("bio") or "") if animal else 0
        desc_len = len(animal.get("description") or "") if animal else 0
        
        # Check eligibility
        eligible = False
        if is_active and shelter_id:
            s_id_upper = shelter_id.upper()
            if s_id_upper in ("NYCACC", "MUDDYPAWS", "PIMA"):
                eligible = bio_len >= 1500 or desc_len >= 1500
            elif s_id_upper == "HSSA":
                eligible = bio_len >= 500 or desc_len >= 500
            else:
                eligible = max(bio_len, desc_len) > 400
                
        print(f"Dog ID: {aid}")
        print(f"  Updated At: {updated_at}")
        print(f"  Active:     {is_active} (shelter: {shelter_id})")
        print(f"  Bio length: {bio_len}")
        print(f"  Desc length:{desc_len}")
        print(f"  Eligible:   {eligible}")
        print("-" * 40)
        
    return 0

if __name__ == "__main__":
    main()
