import os
import json
import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ── Beta location restriction ─────────────────────────────────────────
# Shelter IDs listed here are only visible to the allowed emails.
# To make a shelter public, remove it from BETA_SHELTER_IDS.
BETA_SHELTER_IDS = {"MV"}
BETA_ALLOWED_EMAILS = {"reedr1208@gmail.com"}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            supabase_url = os.environ.get("SUPABASE_URL") or os.environ.get("storage_SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY")
            
            if not supabase_url or not supabase_key:
                raise ValueError("Missing Supabase credentials")

            # Parse email from query string for beta access check
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            user_email = (params.get("email", [None])[0] or "").strip().lower()
            is_beta_user = user_email in BETA_ALLOWED_EMAILS

            client = create_client(supabase_url, supabase_key)
            
            res = client.table("shelters").select("shelter_id, location_display_name, relative_path").execute()
            
            locations_map = {}
            for row in res.data:
                shelter_id = row.get("shelter_id", "")
                disp = row.get("location_display_name")
                if not disp:
                    continue
                # Skip beta-restricted shelters for non-beta users
                if shelter_id in BETA_SHELTER_IDS and not is_beta_user:
                    continue
                if disp not in locations_map:
                    locations_map[disp] = {
                        "display_name": disp,
                        "relative_path": row.get("relative_path") or "",
                        "shelter_ids": []
                    }
                locations_map[disp]["shelter_ids"].append(shelter_id)
                
            locations = list(locations_map.values())
            locations.sort(key=lambda x: x["display_name"])
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"locations": locations}).encode())
        except Exception as e:
            logging.error(f"Error fetching locations: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
