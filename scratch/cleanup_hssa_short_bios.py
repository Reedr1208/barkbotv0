import os
from supabase import create_client

supabase_url = os.environ.get("storage_SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not supabase_key:
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    supabase_url = os.environ.get("storage_SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(supabase_url, supabase_key)

def run():
    print("Fetching active HSSA dogs...")
    res = supabase.table("active_dogs").select("animal_id, shelter_id").eq("shelter_id", "HSSA").execute()
    hssa_ids = [d["animal_id"] for d in res.data] if res.data else []
    
    if not hssa_ids:
        print("No HSSA dogs found.")
        return
        
    print(f"Found {len(hssa_ids)} active HSSA dogs.")
    
    res = supabase.table("animals").select("animal_id, bio").in_("animal_id", hssa_ids).execute()
    animals = res.data or []
    
    invalid_ids = []
    for a in animals:
        bio_len = len(a.get("bio") or "")
        if bio_len < 500:
            invalid_ids.append(a["animal_id"])
            
    print(f"Found {len(invalid_ids)} HSSA dogs with bio_len < 500.")
    
    if invalid_ids:
        for chunk in [invalid_ids[i:i+50] for i in range(0, len(invalid_ids), 50)]:
            res = supabase.table("animal_fact_profiles").delete().in_("animal_id", chunk).execute()
            print(f"Deleted {len(res.data) if res.data else 0} from animal_fact_profiles")
            
            res = supabase.table("system_prompts_v2").delete().in_("animal_id", chunk).execute()
            print(f"Deleted {len(res.data) if res.data else 0} from system_prompts_v2")
            
            res = supabase.table("animal_persona_profiles").delete().in_("animal_id", chunk).execute()
            print(f"Deleted {len(res.data) if res.data else 0} from animal_persona_profiles")

if __name__ == "__main__":
    run()
