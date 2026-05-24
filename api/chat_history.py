"""
/api/chat_history — GET and list endpoints for persistent chat conversations

GET /api/chat_history?email=...                          → list all conversations for the user
GET /api/chat_history?email=...&animal_id=...            → message history for a specific dog
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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            email = (qs.get("email") or [None])[0]
            animal_id = (qs.get("animal_id") or [None])[0]

            if not email:
                self._send_response(400, {"error": "email is required"})
                return

            sb = get_supabase_client()

            if animal_id:
                # Return message history for a specific dog
                conv_res = sb.table("chat_conversations") \
                    .select("id") \
                    .eq("email", email) \
                    .eq("animal_id", animal_id) \
                    .limit(1) \
                    .execute()

                if not conv_res.data:
                    self._send_response(200, {"messages": [], "conversation_id": None})
                    return

                conv_id = conv_res.data[0]["id"]
                msg_res = sb.table("chat_messages") \
                    .select("role, content, created_at") \
                    .eq("conversation_id", conv_id) \
                    .order("created_at", desc=False) \
                    .execute()

                self._send_response(200, {
                    "conversation_id": conv_id,
                    "messages": msg_res.data or []
                })
            else:
                # Return list of all conversations (for Recent Chats tab)
                conv_res = sb.table("chat_conversations") \
                    .select("animal_id, dog_name, dog_image_url, last_message_preview, updated_at") \
                    .eq("email", email) \
                    .order("updated_at", desc=True) \
                    .limit(20) \
                    .execute()

                self._send_response(200, {"conversations": conv_res.data or []})

        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
