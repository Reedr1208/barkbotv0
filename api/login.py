import json
import os
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
            
            email = body.get("email", "").strip().lower()
            if not email:
                self._send_response(400, {"error": "Email is required."})
                return
                
            client = get_supabase_client()
            
            # Fetch existing preferences
            res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()
            
            if res.data:
                profile = res.data[0]
            else:
                # frictionless register: create new profile with defaults
                new_profile = {
                    "email": email,
                    "gender": "any",
                    "age_group": "any",
                    "size": "any",
                    "location": "any"
                }
                insert_res = client.table("user_preferences").insert(new_profile).execute()
                if not insert_res.data:
                    self._send_response(500, {"error": "Failed to create user profile."})
                    return
                profile = insert_res.data[0]
                
            self._send_response(200, profile)
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
