"""
Image download and upload utilities.

Consolidates guess_extension(), download_image_bytes(), and upload_image()
that were copy-pasted in every profiles scraper.
"""

from typing import Optional, Tuple
from urllib.parse import urlparse

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def guess_extension(content_type: Optional[str], image_url: str) -> str:
    """Determine file extension from Content-Type header or URL path."""
    if content_type:
        ct = content_type.lower()
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"

    path = urlparse(image_url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if path.endswith(ext):
            return ext
    return ".jpg"


def download_image_bytes(
    image_url: str,
    headers: dict | None = None,
) -> Tuple[bytes, str]:
    """Download an image and return (content_bytes, file_extension)."""
    hdrs = headers or DEFAULT_HEADERS
    response = requests.get(image_url, headers=hdrs, timeout=30)
    response.raise_for_status()
    ext = guess_extension(response.headers.get("Content-Type"), image_url)
    return response.content, ext


def upload_image(
    client,
    bucket: str,
    animal_id: str,
    image_url: Optional[str],
    headers: dict | None = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Download an image and upload it to Supabase Storage.

    Returns (object_path, public_url) or (None, None) if image_url is falsy.
    This is the standalone version used by "all-in-one" scrapers (MP, WWLA).
    """
    if not image_url:
        return None, None
    try:
        hdrs = headers or DEFAULT_HEADERS
        response = requests.get(image_url, headers=hdrs, timeout=30)
        response.raise_for_status()
        ext = guess_extension(response.headers.get("Content-Type", ""), image_url)
        object_path = f"animals/{animal_id}{ext}"

        client.storage.from_(bucket).upload(
            object_path,
            response.content,
            file_options={
                "upsert": "true",
                "content-type": response.headers.get("Content-Type", "image/jpeg"),
            },
        )
        public_url = client.storage.from_(bucket).get_public_url(object_path)
        return object_path, public_url
    except Exception as e:
        import logging
        logging.error(f"Failed to upload image for {animal_id}: {e}")
        return None, None
