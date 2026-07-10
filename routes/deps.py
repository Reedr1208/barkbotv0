"""
Shared dependencies for FastAPI routes.

Centralizes the Supabase client creation that was previously duplicated
across every api/*.py handler.
"""

import os
from supabase import create_client


def get_supabase_client():
    """Create and return a Supabase client using environment variables."""
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)


def get_supabase_url():
    """Return the Supabase project URL."""
    return os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")


def get_image_base_url():
    """Return the base URL for animal images in Supabase storage."""
    url = get_supabase_url()
    bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
    return f"{url}/storage/v1/object/public/{bucket}/"
