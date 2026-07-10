"""
FastAPI routes for the /dogs/ SSR HTML pages.

Replaces api/dog_meta.py — serves pre-rendered HTML with injected OG meta
tags for social sharing. The business logic (meta tag injection, profile
lookup) is identical to the original.
"""

import html
import json
import os
import re
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.deps import get_supabase_client, get_image_base_url

router = APIRouter()
logger = logging.getLogger("barkbot.dog_meta")

CANONICAL_ORIGIN = "https://chattyhound.com"
_INDEX_HTML_CACHE = None
DEFAULT_OG_IMAGE = f"{CANONICAL_ORIGIN}/chattyhound_og.png"


def _clean_age(age_str):
    if not age_str:
        return ""
    clean = re.sub(r"The shelter staff think I am", "", age_str, flags=re.I)
    clean = re.sub(r"\bold\b", "", clean, flags=re.I).strip()
    clean = re.sub(r"^(?:about|around)\s+", "", clean, flags=re.I)
    return clean.strip()


def _pronoun(gender_str):
    g = (gender_str or "").lower()
    if "female" in g:
        return "her"
    if "male" in g:
        return "him"
    return "them"


def _dog_image_url(profile):
    if profile.get("image_file") and profile.get("image_base_url"):
        return profile["image_base_url"] + profile["image_file"]
    if profile.get("image_public_url"):
        return profile["image_public_url"]
    if profile.get("shelter_image_url"):
        return profile["shelter_image_url"]
    return DEFAULT_OG_IMAGE


def _build_meta_copy(profile):
    name = profile.get("name") or "This pup"
    age = _clean_age(profile.get("age") or "")
    shelter = profile.get("shelter_name") or "Pima Animal Care Center"
    pron = _pronoun(profile.get("gender"))
    breed_label = (profile.get("breed_or_description") or "rescue mix").lower()

    title = f"Meet {name} | ChattyHound"
    og_title = f"Meet {name} on ChattyHound"

    age_part = f"{age} " if age else ""
    description = (
        f"{name} is an adoptable rescue dog at {shelter}. "
        f"Chat with {pron} on ChattyHound and continue to the official shelter page."
    )
    share_text = (
        f"{name} is a sweet {age_part}{breed_label} at {shelter}. "
        f"Chat with {pron} and learn more on ChattyHound."
    ).replace("  ", " ").strip()

    return {
        "title": title,
        "og_title": og_title,
        "description": description,
        "share_text": share_text,
    }


def _fetch_dog_profile(animal_id):
    client = get_supabase_client()
    active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight").eq("animal_id", animal_id).limit(1).execute()
    prompts_res = client.table("animal_fact_profiles").select("animal_id, dog_name, breed_or_description, important_facts_jsonb").eq("animal_id", animal_id).limit(1).execute()
    profile_res = client.table("animals").select("*").eq("animal_id", animal_id).limit(1).execute()

    if not active_res.data or not profile_res.data:
        return None

    active_dog = active_res.data[0]
    profile = profile_res.data[0]
    fact_data = prompts_res.data[0] if prompts_res.data else {}
    profile["name"] = fact_data.get("dog_name") or active_dog.get("name") or "Unknown"
    profile["gender"] = active_dog.get("gender") or "Unknown"
    profile["important_facts"] = prompts_res.data[0].get("important_facts_jsonb", []) if prompts_res.data else []
    profile["breed_or_description"] = fact_data.get("breed_or_description") or "Rescue Mix"
    profile["image_base_url"] = get_image_base_url()
    return profile


def _inject_head(html_text, meta, dog_id, image_url, location_path=None):
    if location_path and dog_id:
        canonical = f"{CANONICAL_ORIGIN}/dogs{location_path}/{dog_id}"
    elif location_path:
        canonical = f"{CANONICAL_ORIGIN}/dogs{location_path}"
    elif dog_id:
        canonical = f"{CANONICAL_ORIGIN}/dogs/{dog_id}"
    else:
        canonical = CANONICAL_ORIGIN
    esc = html.escape
    desc = esc(meta["description"])
    title = esc(meta["title"])
    og_title = esc(meta["og_title"])
    img = esc(image_url)

    out = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>", html_text, count=1)
    out = re.sub(
        r'<meta name="description"\s+content="[^"]*">',
        f'<meta name="description" content="{desc}">',
        out, count=1,
    )
    out = out.replace(
        '<link rel="canonical" href="https://chattyhound.com/" />',
        f'<link rel="canonical" href="{canonical}" />',
    )
    out = re.sub(r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{canonical}">', out, count=1)
    out = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="{og_title}">', out, count=1)
    out = re.sub(r'<meta property="og:description"\s+content="[^"]*">', f'<meta property="og:description" content="{desc}">', out, count=1)

    og_image_block = (
        f'<meta property="og:image" content="{img}">\n'
        f'  <meta property="og:image:secure_url" content="{img}">\n'
        f'  <meta property="og:image:alt" content="{esc(meta["og_title"])}">\n'
        f'  <meta property="og:image:type" content="image/jpeg">'
    )
    out = re.sub(
        r'<meta property="og:image" content="[^"]*">\s*'
        r'(?:<meta property="og:image:secure_url" content="[^"]*">\s*)?'
        r'(?:<meta property="og:image:alt" content="[^"]*">\s*)?'
        r'<meta property="og:image:type" content="[^"]*">\s*'
        r'<meta property="og:image:width" content="[^"]*">\s*'
        r'<meta property="og:image:height" content="[^"]*">',
        og_image_block
        + '\n  <meta property="og:image:width" content="1024">'
        + '\n  <meta property="og:image:height" content="1024">',
        out, count=1,
    )
    out = re.sub(r'<meta property="twitter:url" content="[^"]*">', f'<meta property="twitter:url" content="{canonical}">', out, count=1)
    out = re.sub(r'<meta property="twitter:title" content="[^"]*">', f'<meta property="twitter:title" content="{og_title}">', out, count=1)
    out = re.sub(r'<meta property="twitter:description"\s+content="[^"]*">', f'<meta property="twitter:description" content="{desc}">', out, count=1)
    out = re.sub(r'<meta property="twitter:image" content="[^"]*">', f'<meta property="twitter:image" content="{img}">', out, count=1)

    extra = "window.__CH_DOG_UNAVAILABLE__=true;" if meta.get("unavailable") else ""
    loc_js = f"window.__CH_INITIAL_LOCATION__={json.dumps(location_path)};" if location_path else ""
    bootstrap = (
        f'<script>{extra}{loc_js}window.__CH_INITIAL_DOG_ID__={json.dumps(dog_id)};'
        f'window.__CH_PAGE_META__={json.dumps(meta)};</script>\n'
    )
    out = out.replace("<body>", f"<body>\n{bootstrap}", 1)
    return out


def _load_index_html():
    """Load the inlined index.html from the filesystem."""
    global _INDEX_HTML_CACHE
    if _INDEX_HTML_CACHE is not None:
        return _INDEX_HTML_CACHE

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root, "api", "index.html"),
        os.path.join(root, "public", "index.html"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                _INDEX_HTML_CACHE = f.read()
                return _INDEX_HTML_CACHE

    raise RuntimeError(f"index.html not found. Searched: {candidates}")


@router.get("/dogs/{path1}/{path2}")
async def dog_meta_two_parts(path1: str, path2: str, request: Request):
    """Handle /dogs/<location>/<dog_id> or /dogs/<path1>/<path2>."""
    return await _handle_dog_meta(request, path1, path2)


@router.get("/dogs/{path1}")
async def dog_meta_one_part(path1: str, request: Request):
    """Handle /dogs/<dog_id> or /dogs/<location>."""
    return await _handle_dog_meta(request, path1, "")


async def _handle_dog_meta(request: Request, path1: str, path2: str):
    """Core logic for the /dogs/ SSR route."""
    try:
        dog_id = ""
        location_path = None

        client = get_supabase_client()

        if path1:
            if path1 == "alldogs":
                location_path = "/alldogs"
                if path2:
                    dog_id = path2
            else:
                shelters_res = client.table("shelters").select("relative_path").eq("relative_path", "/" + path1).limit(1).execute()
                if shelters_res.data:
                    location_path = "/" + path1
                    if path2:
                        dog_id = path2
                else:
                    if not dog_id:
                        dog_id = path1

        if location_path and not dog_id:
            html_text = _load_index_html()
            meta = {
                "title": "ChattyHound",
                "og_title": "ChattyHound",
                "description": "Meet adoptable rescue dogs.",
                "share_text": "",
            }
            html_out = _inject_head(html_text, meta, "", DEFAULT_OG_IMAGE, location_path)
            return HTMLResponse(content=html_out, headers={"Cache-Control": "public, max-age=300"})

        if not dog_id:
            return RedirectResponse(url="/")

        html_text = _load_index_html()

        profile = _fetch_dog_profile(dog_id)
        if not profile:
            unavailable_meta = {
                "title": "Dog unavailable | ChattyHound",
                "og_title": "Dog unavailable | ChattyHound",
                "description": "This dog may no longer be available. Meet other adoptable dogs on ChattyHound.",
                "share_text": "",
                "unavailable": True,
            }
            html_out = _inject_head(html_text, unavailable_meta, dog_id, DEFAULT_OG_IMAGE, location_path)
            return HTMLResponse(content=html_out, headers={"Cache-Control": "public, max-age=300"})

        meta = _build_meta_copy(profile)
        image_url = _dog_image_url(profile)
        html_out = _inject_head(html_text, meta, dog_id, image_url, location_path)
        return HTMLResponse(content=html_out, headers={"Cache-Control": "public, max-age=300"})

    except Exception as e:
        return HTMLResponse(content=str(e), status_code=500)
