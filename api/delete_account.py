"""
/api/delete_account — POST: permanently delete all data tied to an email.

Body: {"email": "user@example.com"}
Returns: {"status": "deleted"}

Purpose: satisfies Apple App Store Guideline 5.1.1(v), which requires an in-app
way for users to delete the account/data they created (the mobile app calls this
when a user taps "Delete my account & data").

Deletes, in FK-safe order, for the given email:
  chat_messages -> chat_conversations -> saved_dogs -> user_preferences

────────────────────────────────────────────────────────────────────────────
⚠️  SECURITY REVIEW REQUIRED BEFORE PRODUCTION DEPLOY  ⚠️
This endpoint performs irreversible production data deletion and, like the rest
of the current API, identifies the user only by a plaintext email (no verified
session/token). As written, anyone who knows an email could delete that user's
data. Before shipping to prod you should:
  • gate deletion behind a verified identity (e.g. email one-time code, or the
    same auth you adopt for login), and/or
  • require a short-lived confirmation token issued to the account's email.
Have Security review this before enabling it in production.
────────────────────────────────────────────────────────────────────────────
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
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-type")
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_response(400, {"error": "Empty request body."})
                return

            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            email = (body.get("email") or "").strip().lower()
            if not email:
                self._send_response(400, {"error": "email is required"})
                return

            sb = get_supabase_client()

            # 1) chat_messages — referenced by conversation_id, so look those up first.
            convo_res = sb.table("chat_conversations").select("id").eq("email", email).execute()
            convo_ids = [c["id"] for c in (convo_res.data or []) if c.get("id") is not None]
            if convo_ids:
                sb.table("chat_messages").delete().in_("conversation_id", convo_ids).execute()

            # 2) conversations, 3) saved dogs, 4) preferences — all keyed by email.
            sb.table("chat_conversations").delete().eq("email", email).execute()
            sb.table("saved_dogs").delete().eq("email", email).execute()
            sb.table("user_preferences").delete().eq("email", email).execute()

            self._send_response(200, {"status": "deleted"})

        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
