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
    
    print("Fetching active_dogs...")
    active_res = client.table("active_dogs").select("animal_id, shelter_id").execute()
    active_dogs = {row["animal_id"]: row["shelter_id"] for row in active_res.data}
    
    print("Fetching animals...")
    animals_res = client.table("animals").select("animal_id, bio, description").execute()
    animals = {row["animal_id"]: row for row in animals_res.data}
    
    print("Fetching system_prompts_v2...")
    prompts_res = client.table("system_prompts_v2").select("animal_id, updated_at").execute()
    prompts = {row["animal_id"]: row["updated_at"] for row in prompts_res.data}
    
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    
    shelters = {}
    
    # Analyze every active dog
    for aid, shelter_id in active_dogs.items():
        if not shelter_id:
            continue
        s_id = shelter_id.upper()
        if s_id not in shelters:
            shelters[s_id] = {
                "active": 0,
                "eligible": 0,
                "has_prompt": 0,
                "missing_prompt": 0,
                "stale_prompt": 0,
                "fresh_prompt": 0
            }
            
        shelters[s_id]["active"] += 1
        
        # Check eligibility
        animal = animals.get(aid)
        bio = animal.get("bio") or "" if animal else ""
        desc = animal.get("description") or "" if animal else ""
        bio_len = len(bio)
        desc_len = len(desc)
        
        eligible = False
        if s_id in ("NYCACC", "MUDDYPAWS", "PIMA"):
            eligible = bio_len >= 1500 or desc_len >= 1500
        elif s_id == "HSSA":
            eligible = bio_len >= 500 or desc_len >= 500
        else:
            eligible = max(bio_len, desc_len) > 400
            
        if eligible:
            shelters[s_id]["eligible"] += 1
            
            if aid in prompts:
                shelters[s_id]["has_prompt"] += 1
                
                updated_at_str = prompts[aid]
                if updated_at_str.endswith("Z"):
                    updated_at_str = updated_at_str[:-1] + "+00:00"
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                except ValueError:
                    updated_at = datetime.min.replace(tzinfo=timezone.utc)
                    
                if updated_at < three_days_ago:
                    shelters[s_id]["stale_prompt"] += 1
                else:
                    shelters[s_id]["fresh_prompt"] += 1
            else:
                shelters[s_id]["missing_prompt"] += 1
                
    print("\nBacklog Analysis by Shelter:")
    print("-" * 80)
    print(f"{'Shelter':<12} | {'Active':<8} | {'Eligible':<8} | {'Has Prompt':<10} | {'Missing':<8} | {'Stale':<8} | {'Fresh':<8}")
    print("-" * 80)
    for s_id, stats in sorted(shelters.items()):
        print(f"{s_id:<12} | {stats['active']:<8} | {stats['eligible']:<8} | {stats['has_prompt']:<10} | {stats['missing_prompt']:<8} | {stats['stale_prompt']:<8} | {stats['fresh_prompt']:<8}")
    print("-" * 80)

if __name__ == "__main__":
    main()
