import json
import os
import random
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta
from supabase import create_client

def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)

def parse_weight_lbs(weight_str):
    if not weight_str:
        return 0.0
    match = re.search(r'(\d+(?:\.\d+)?)', weight_str)
    if not match:
        return 0.0
    try:
        val = float(match.group(1))
        if "kg" in weight_str.lower():
            val = val * 2.20462
        return val
    except ValueError:
        return 0.0

def classify_age_group(age_str):
    if not age_str:
        return "any"
    age_str = age_str.lower()
    
    years = 0
    months = 0
    
    matches = re.findall(r'(\d+)\s*(year|month|week|day)', age_str)
    for val_str, unit in matches:
        val = int(val_str)
        if "year" in unit:
            years = val
        elif "month" in unit:
            months = val
            
    if years == 0 and months > 0:
        return "puppy"
    elif years == 0:
        return "puppy"
    elif years < 1:
        return "puppy"
    elif years <= 3:
        return "young"
    elif years < 8:
        return "adult"
    else:
        return "senior"

def matches_gender(dog_gender, pref_gender):
    if not pref_gender or pref_gender == "any":
        return True
    if not dog_gender:
        return False
    dog_gender = dog_gender.lower().strip()
    pref_gender = pref_gender.lower().strip()
    
    if pref_gender == "male":
        return "female" not in dog_gender and "male" in dog_gender
    return pref_gender in dog_gender

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            viewed_str = query_params.get("viewed", [""])[0]
            viewed_ids = set(filter(None, viewed_str.split(",")))
            email = query_params.get("email", [""])[0].strip().lower()

            client = get_supabase_client()
            
            # Fetch all dog IDs, names, and filterable fields from pima_all_dogs
            pima_res = client.table("pima_all_dogs").select("animal_id, name, gender, age, weight").execute()
            if not pima_res.data:
                self._send_response(404, {"error": "No dogs found in pima_all_dogs."})
                return
            pima_dogs = {row["animal_id"]: row for row in pima_res.data}
            
            # Fetch from system_prompts
            prompts_res = client.table("system_prompts").select("animal_id, updated_at, important_facts").execute()
            prompts_data = {row["animal_id"]: row for row in prompts_res.data}
            
            # Intersect to find valid current dogs that have a system_prompt
            valid_ids = list(set(pima_dogs.keys()).intersection(prompts_data.keys()))
            if not valid_ids:
                self._send_response(404, {"error": "No dogs with generated prompts found."})
                return

            # Fetch user preferences if logged in
            preferences = None
            if email:
                pref_res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()
                if pref_res.data:
                    preferences = pref_res.data[0]

            # Apply preferences filtering if preferences are configured
            filtered_ids = []
            preferences_matched = False
            
            if preferences:
                pref_gender = preferences.get("gender", "any")
                pref_age = preferences.get("age_group", "any")
                pref_size = preferences.get("size", "any")
                
                # Check if they have set any actual preference filters
                has_active_prefs = (pref_gender != "any" or pref_age != "any" or pref_size != "any")
                
                if has_active_prefs:
                    for aid in valid_ids:
                        dog = pima_dogs[aid]
                        
                        # 1. Gender Filter
                        if not matches_gender(dog.get("gender"), pref_gender):
                            continue
                            
                        # 2. Age Filter
                        if pref_age != "any":
                            dog_age_group = classify_age_group(dog.get("age"))
                            if dog_age_group != pref_age:
                                continue
                                
                        # 3. Size Filter
                        if pref_size != "any":
                            dog_weight = parse_weight_lbs(dog.get("weight"))
                            is_match = False
                            if pref_size == "small":
                                is_match = dog_weight > 0 and dog_weight < 25
                            elif pref_size == "medium":
                                is_match = dog_weight >= 25 and dog_weight < 60
                            elif pref_size == "large":
                                is_match = dog_weight >= 60
                            if not is_match:
                                continue
                                
                        filtered_ids.append(aid)
                    
                    if filtered_ids:
                        valid_ids = filtered_ids
                        preferences_matched = True

            # Categorize into fresh and stale
            three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
            fresh_ids = []
            stale_ids = []
            
            for aid in valid_ids:
                dt_str = prompts_data[aid].get("updated_at", "")
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                try:
                    updated_at = datetime.fromisoformat(dt_str)
                    if updated_at >= three_days_ago:
                        fresh_ids.append(aid)
                    else:
                        stale_ids.append(aid)
                except Exception:
                    fresh_ids.append(aid) # default to fresh
                    
            unviewed_fresh = [aid for aid in fresh_ids if aid not in viewed_ids]
            unviewed_stale = [aid for aid in stale_ids if aid not in viewed_ids]
            
            if unviewed_fresh:
                random_id = random.choice(unviewed_fresh)
            elif unviewed_stale:
                random_id = random.choice(unviewed_stale)
            else:
                # All viewed. Reset pool, prioritize fresh.
                if fresh_ids:
                    random_id = random.choice(fresh_ids)
                else:
                    random_id = random.choice(stale_ids)
            
            # Fetch the full profile
            profile_res = client.table("animals").select("*").eq("animal_id", random_id).limit(1).execute()
            if not profile_res.data:
                self._send_response(404, {"error": "Profile not found in animals table."})
                return
                
            profile = profile_res.data[0]
            
            # Add the name and facts
            profile["name"] = pima_dogs[random_id].get("name") or "Unknown"
            profile["important_facts"] = prompts_data[random_id].get("important_facts", [])
            profile["preferences_matched"] = preferences_matched
            profile["user_has_preferences"] = (preferences is not None)
            
            # Clean up internal fields before sending to frontend
            internal_keys = ["id", "record_hash", "qa_status", "qa_notes", "created_at", "updated_at", "last_scrape_run_id", "data_updated"]
            for key in internal_keys:
                profile.pop(key, None)
                
            supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
            profile["image_base_url"] = f"{supabase_url}/storage/v1/object/public/{bucket}/"
                
            self._send_response(200, profile)
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
