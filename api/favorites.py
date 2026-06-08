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
            res = sb.table("saved_dogs").select("animal_id, created_at").eq("email", email).order("created_at", desc=True).execute()
            saved_records = res.data or []

            if not saved_records:
                self._send_response(200, {"saved": []})
                return

            animal_ids = [r["animal_id"] for r in saved_records]

            # Fetch from active_dogs to get breed/mix, name, gender, age, weight
            active_res = sb.table("active_dogs").select("animal_id, name, gender, age, weight").in_("animal_id", animal_ids).execute()
            active_map = {p["animal_id"]: p for p in (active_res.data or [])}

            # Fetch from animals to get shelter_name, shelter_profile_url, image_file, image_public_url, shelter_image_url
            animals_res = sb.table("animals").select("animal_id, shelter_name, shelter_profile_url, image_file, image_public_url, shelter_image_url").in_("animal_id", animal_ids).execute()
            animals_map = {a["animal_id"]: a for a in (animals_res.data or [])}

            saved_dogs_rich = []
            supabase_url_val = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "https://yiqiotjoyiedrwznmhgh.supabase.co"
            bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
            image_base_url = f"{supabase_url_val}/storage/v1/object/public/{bucket}/"

            for r in saved_records:
                aid = r["animal_id"]
                active_dog = active_map.get(aid, {})
                animal = animals_map.get(aid, {})

                # Determine dynamic image url
                dog_image_url = ""
                if animal.get("image_file"):
                    dog_image_url = image_base_url + animal["image_file"]
                elif animal.get("image_public_url"):
                    dog_image_url = animal["image_public_url"]
                elif animal.get("shelter_image_url"):
                    dog_image_url = animal["shelter_image_url"]
                elif active_dog.get("image_url"):
                    dog_image_url = active_dog["image_url"]

                saved_dogs_rich.append({
                    "animal_id": aid,
                    "created_at": r["created_at"],
                    "dog_name": active_dog.get("name") or "Shelter Pup",
                    "gender": active_dog.get("gender") or "Unknown",
                    "age": active_dog.get("age") or "Unknown",
                    "weight": active_dog.get("weight") or "Unknown",
                    "shelter_name": animal.get("shelter_name") or "Pima Animal Care Center",
                    "shelter_profile_url": animal.get("shelter_profile_url") or "",
                    "dog_image_url": dog_image_url
                })

            self._send_response(200, {"saved": saved_dogs_rich})

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
