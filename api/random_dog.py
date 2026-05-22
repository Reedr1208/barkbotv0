import json
import os
import random
from http.server import BaseHTTPRequestHandler
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
            client = get_supabase_client()
            
            # Fetch all dog IDs and names from current pima_all_dogs
            pima_res = client.table("pima_all_dogs").select("animal_id, name").execute()
            if not pima_res.data:
                self._send_response(404, {"error": "No dogs found in pima_all_dogs."})
                return
            
            pima_dogs = {row["animal_id"]: row["name"] for row in pima_res.data}
            
            # Fetch all dog IDs from historical detailed animals
            animals_res = client.table("animals").select("animal_id").execute()
            animal_ids = {row["animal_id"] for row in animals_res.data}
            
            # Intersect to find valid current dogs that have a detailed profile
            valid_ids = list(animal_ids.intersection(pima_dogs.keys()))
            
            if not valid_ids:
                self._send_response(404, {"error": "No matching dogs found between tables."})
                return
                
            random_id = random.choice(valid_ids)
            
            # Fetch the full profile
            profile_res = client.table("animals").select("*").eq("animal_id", random_id).limit(1).execute()
            
            if not profile_res.data:
                self._send_response(404, {"error": "Profile not found."})
                return
                
            profile = profile_res.data[0]
            
            # Add the name from pima_all_dogs
            profile["name"] = pima_dogs[random_id]
            
            # Clean up internal fields before sending to frontend
            internal_keys = ["id", "record_hash", "qa_status", "qa_notes", "created_at", "updated_at", "last_scrape_run_id", "data_updated"]
            for key in internal_keys:
                profile.pop(key, None)
                
            # If image_file exists, the frontend can construct the url, but let's provide a helpful base_url
            supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
            profile["image_base_url"] = f"{supabase_url}/storage/v1/object/public/{bucket}/"
                
            self._send_response(200, profile)
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        # Allow CORS if needed
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
