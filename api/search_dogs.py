"""
GET /api/search_dogs — Returns all chat-eligible dogs for client-side name search.

Response: { dogs: [{ id, name, image_url, shelter_id, city, state }] }

Eligible = active_dogs ∩ animal_persona_profiles ∩ system_prompts_v2
"""

import os
import json
from http.server import BaseHTTPRequestHandler

def fetch_all_rows(query):
    all_rows = []
    offset = 0
    while True:
        res = query.range(offset, offset + 999).execute()
        all_rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    return all_rows


class handler(BaseHTTPRequestHandler):
    def _send_response(self, code, body):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_GET(self):
        try:
            from jobs.lib.db import get_supabase_client

            client = get_supabase_client()

            image_base_url = os.environ.get(
                "SUPABASE_IMAGE_BASE_URL",
                os.environ.get(
                    "storage_SUPABASE_URL",
                    "https://yiqiotjoyiedrwznmhgh.supabase.co",
                ),
            )
            if "/storage/" not in image_base_url:
                image_base_url = (
                    image_base_url.rstrip("/")
                    + "/storage/v1/object/public/animal-images/"
                )

            # Fetch all active dogs (name + shelter_id)
            active_list = fetch_all_rows(
                client.table("active_dogs").select("animal_id, name, shelter_id")
            )
            active_map = {r["animal_id"]: r for r in active_list}

            # Fetch persona IDs (eligibility gate)
            persona_list = fetch_all_rows(
                client.table("animal_persona_profiles").select("animal_id")
            )
            persona_ids = {r["animal_id"] for r in persona_list}

            # Fetch prompt IDs (eligibility gate)
            prompt_list = fetch_all_rows(
                client.table("system_prompts_v2").select("animal_id")
            )
            prompt_ids = {r["animal_id"] for r in prompt_list}

            # Fetch fact profiles for dog_name overrides
            fact_list = fetch_all_rows(
                client.table("animal_fact_profiles").select("animal_id, dog_name")
            )
            fact_names = {r["animal_id"]: r.get("dog_name") for r in fact_list}

            # Fetch shelters for city/state
            shelters_res = client.table("shelters").select("shelter_id, city, state").execute()
            shelters_map = {s["shelter_id"]: s for s in shelters_res.data}

            # Fetch actual image paths from animals table
            img_list = fetch_all_rows(
                client.table("animals").select("animal_id, image_file")
            )
            img_map = {r["animal_id"]: r.get("image_file") for r in img_list}

            # Intersect for eligibility
            eligible_ids = set(active_map.keys()) & persona_ids & prompt_ids

            dogs = []
            for aid in eligible_ids:
                dog = active_map[aid]
                shelter = shelters_map.get(dog.get("shelter_id"), {})
                name = fact_names.get(aid) or dog.get("name") or "Unknown"
                img_file = img_map.get(aid)
                image_url = f"{image_base_url}{img_file}" if img_file else ""
                dogs.append({
                    "id": aid,
                    "name": name,
                    "image_url": image_url,
                    "shelter_id": dog.get("shelter_id", ""),
                    "city": shelter.get("city", ""),
                    "state": shelter.get("state", ""),
                })

            # Sort alphabetically by name
            dogs.sort(key=lambda d: d["name"].lower())

            self._send_response(200, {"dogs": dogs, "count": len(dogs)})

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_response(500, {"error": str(e)})
