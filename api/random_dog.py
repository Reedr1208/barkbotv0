import json
import os
import random
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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            viewed_str = query_params.get("viewed", [""])[0]
            viewed_ids = set(filter(None, viewed_str.split(",")))

            client = get_supabase_client()
            
            # Fetch all dog IDs and names from current pima_all_dogs
            pima_res = client.table("pima_all_dogs").select("animal_id, name").execute()
            if not pima_res.data:
                self._send_response(404, {"error": "No dogs found in pima_all_dogs."})
                return
            pima_dogs = {row["animal_id"]: row["name"] for row in pima_res.data}
            
            # Fetch from system_prompts
            prompts_res = client.table("system_prompts").select("animal_id, updated_at, important_facts").execute()
            prompts_data = {row["animal_id"]: row for row in prompts_res.data}
            
            # Intersect to find valid current dogs that have a system_prompt
            valid_ids = list(set(pima_dogs.keys()).intersection(prompts_data.keys()))
            if not valid_ids:
                self._send_response(404, {"error": "No dogs with generated prompts found."})
                return
                
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
            
            # Add the name from pima_all_dogs
            profile["name"] = pima_dogs[random_id]
            # Add important_facts from system_prompts
            profile["important_facts"] = prompts_data[random_id].get("important_facts", [])
            
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
