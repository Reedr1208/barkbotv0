import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(url, key)

res = client.table("chat_conversations").upsert({
    "email": "test_guest@guest.chattyhound.com",
    "animal_id": "A1234567",
    "dog_name": "Test",
    "dog_image_url": "",
    "last_message_preview": "test",
    "updated_at": "now()"
}).execute()
print(res.data)
