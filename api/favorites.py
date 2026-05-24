"""
/api/favorites — GET, POST, DELETE for saved dogs (hearts)

GET  /api/favorites?email=...          → returns [{animal_id, dog_name, dog_image_url, created_at}, ...]
POST /api/favorites                    → body: {email, animal_id, dog_name, dog_image_url, action: "save"|"remove"}
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            email = (qs.get("email") or [None])[0]

            if not email:
                self._send_response(400, {"error": "email is required"})
                return

            sb = get_supabase_client()
            res = sb.table("saved_dogs").select("*").eq("email", email).order("created_at", desc=True).execute()
            self._send_response(200, {"saved": res.data or []})

        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_response(400, {"error": "Empty request body."})
                return

            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            email = (body.get("email") or "").strip().lower()
            animal_id = (body.get("animal_id") or "").strip()
            action = body.get("action", "save")

            if not email or not animal_id:
                self._send_response(400, {"error": "email and animal_id are required"})
                return

            sb = get_supabase_client()

            if action == "remove":
                sb.table("saved_dogs").delete().eq("email", email).eq("animal_id", animal_id).execute()
                self._send_response(200, {"status": "removed"})
            else:
                # Upsert: save the dog
                dog_name = body.get("dog_name") or ""
                dog_image_url = body.get("dog_image_url") or ""
                row = {
                    "email": email,
                    "animal_id": animal_id,
                    "dog_name": dog_name,
                    "dog_image_url": dog_image_url,
                }
                sb.table("saved_dogs").upsert(row, on_conflict="email,animal_id").execute()
                self._send_response(200, {"status": "saved"})

        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
