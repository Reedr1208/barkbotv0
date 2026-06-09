import os
import json
import logging
from http.server import BaseHTTPRequestHandler
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            supabase_url = os.environ.get("SUPABASE_URL") or os.environ.get("storage_SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY")
            
            if not supabase_url or not supabase_key:
                raise ValueError("Missing Supabase credentials")
                
            client = create_client(supabase_url, supabase_key)
            
            res = client.table("shelters").select("location_display_name").execute()
            locations = list({row["location_display_name"] for row in res.data if row.get("location_display_name")})
            locations.sort()
            
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
