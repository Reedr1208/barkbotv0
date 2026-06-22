"""
GET /api/suggested_prompts
Returns all Informative and Whimsical suggested prompts from the suggested_prompts table,
grouped by category.
"""

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
    def do_GET(self):
        try:
            client = get_supabase_client()
            res = client.table("suggested_prompts").select("category, prompt_text").execute()

            informative = []
            whimsical = []
            for row in res.data:
                if row["category"] == "Informative":
                    informative.append(row["prompt_text"])
                elif row["category"] == "Whimsical":
                    whimsical.append(row["prompt_text"])

            self._send_response(200, {
                "informative": informative,
                "whimsical": whimsical
            })
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
