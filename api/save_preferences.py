import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from supabase import create_client

def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-type")
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_response(400, {"error": "Empty request body."})
                return
                
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            
            pref_obj = body.get("preferences", body)
            email = body.get("email", "").strip().lower()
            gender = pref_obj.get("gender", "any").strip().lower()
            age_group = pref_obj.get("age_group", "any").strip().lower()
            size = pref_obj.get("size", "any").strip().lower()
            location = pref_obj.get("location", "any").strip()
            
            if not email:
                self._send_response(400, {"error": "Email is required."})
                return
                
            client = get_supabase_client()
            
            # Restrict inputs to known categories
            valid_genders = {"male", "female", "any"}
            valid_ages = {"puppy", "young", "adult", "senior", "any"}
            valid_sizes = {"small", "medium", "large", "any"}
            
            shelters_res = client.table("shelters").select("location_display_name").execute()
            valid_locations = set([s["location_display_name"] for s in shelters_res.data]) if shelters_res.data else set()
            valid_locations.add("any")
            
            if gender not in valid_genders: gender = "any"
            if age_group not in valid_ages: age_group = "any"
            if size not in valid_sizes: size = "any"
            if location not in valid_locations: location = "any"
            
            pref_data = {
                "email": email,
                "gender": gender,
                "age_group": age_group,
                "size": size,
                "location": location,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            upsert_res = client.table("user_preferences").upsert(pref_data, on_conflict="email").execute()
            if not upsert_res.data:
                self._send_response(500, {"error": "Failed to save user preferences."})
                return
                
            self._send_response(200, {"ok": True, "preferences": upsert_res.data[0]})
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
