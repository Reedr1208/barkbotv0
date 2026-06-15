from supabase import create_client
import os

supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

client = create_client(supabase_url, supabase_key)
res = client.table("shelters").select("*").eq("shelter_id", "AHSCN").execute()
print(res.data)
