import json
import os
from http.server import BaseHTTPRequestHandler
from supabase import create_client
from openai import OpenAI

CHAT_MODEL = "gpt-5.4-mini"

from pathlib import Path

def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)


def _upsert_conversation(sb, email, animal_id, dog_name, dog_image_url, last_preview, ip_address="", location=""):
    """Upsert a chat_conversations row and return the conversation id."""
    try:
        row = {
            "email": email,
            "animal_id": animal_id,
            "dog_name": dog_name or "",
            "dog_image_url": dog_image_url or "",
            "last_message_preview": last_preview[:200] if last_preview else "",
            "ip_address": ip_address,
            "location": location,
            "updated_at": "now()",
        }
        res = sb.table("chat_conversations").upsert(row, on_conflict="email,animal_id").execute()
        if res.data:
            return res.data[0]["id"]
        # If upsert didn't return data, fetch it
        fetch = sb.table("chat_conversations") \
            .select("id") \
            .eq("email", email) \
            .eq("animal_id", animal_id) \
            .limit(1).execute()
        return fetch.data[0]["id"] if fetch.data else None
    except Exception:
        return None


def _save_messages(sb, conversation_id, user_message, assistant_reply, ip_address="", location=""):
    """Append user + assistant messages to chat_messages."""
    try:
        sb.table("chat_messages").insert([
            {"conversation_id": conversation_id, "role": "user", "content": user_message, "ip_address": ip_address, "location": location},
            {"conversation_id": conversation_id, "role": "assistant", "content": assistant_reply, "ip_address": ip_address, "location": location},
        ]).execute()
    except Exception:
        pass  # Non-blocking: don't fail the chat if persistence fails


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
            
            animal_id = body.get("animal_id")
            user_message = body.get("message", "")
            conversation_history = body.get("conversation_history", [])
            # Optional persistence fields
            user_email = (body.get("email") or "").strip().lower() or "anonymous@chattyhound.com"
            dog_name = body.get("dog_name") or ""
            dog_image_url = body.get("dog_image_url") or ""
            
            # Vercel IP/Location headers
            ip_address = self.headers.get("x-forwarded-for") or self.headers.get("x-real-ip") or ""
            city = self.headers.get("x-vercel-ip-city")
            country = self.headers.get("x-vercel-ip-country")
            location = f"{city}, {country}" if city and country else (city or country or "")
            
            if not animal_id or not user_message:
                self._send_response(400, {"error": "animal_id and message are required."})
                return
                
            sb_client = get_supabase_client()
            res = sb_client.table("system_prompts_v2").select("system_prompt").eq("animal_id", animal_id).order("created_at", desc=True).limit(1).execute()
            
            if not res.data:
                self._send_response(404, {"error": "System prompt not found for this dog."})
                return
                
            system_prompt = res.data[0]["system_prompt"]
            
            input_messages = [
                {
                    "role": "developer",
                    "content": system_prompt,
                }
            ]
            
            for turn in conversation_history:
                if "role" in turn and "content" in turn:
                    input_messages.append({"role": turn["role"], "content": turn["content"]})
                
            input_messages.append({"role": "user", "content": user_message})
            
            openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            
            try:
                response = openai_client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=input_messages,
                )
                output_text = response.choices[0].message.content
            except AttributeError:
                response = openai_client.responses.create(
                    model=CHAT_MODEL,
                    input=input_messages,
                )
                output_text = response.output_text
            
            # Persist conversation (non-blocking)
            try:
                conv_id = _upsert_conversation(
                    sb_client, user_email, animal_id,
                    dog_name, dog_image_url,
                    output_text[:200],
                    ip_address, location
                )
                if conv_id:
                    _save_messages(sb_client, conv_id, user_message, output_text, ip_address, location)
            except Exception:
                pass  # Never block the chat reply on persistence errors

            self._send_response(200, {"reply": output_text})
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
