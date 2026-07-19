"""
FastAPI routes for all BarkBot JSON API endpoints.

Replaces the 10 BaseHTTPRequestHandler-based handlers in api/*.py with
clean FastAPI route functions. Business logic is preserved exactly;
only the HTTP plumbing changes.
"""

import json
import os
import random
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from routes.deps import get_supabase_client, get_image_base_url

import requests as _requests

router = APIRouter()
logger = logging.getLogger("barkbot.api")

# ── Server-side IP geolocation (replaces Vercel geo-IP headers) ─────
_geoip_cache = {}  # key: IP /24 prefix, value: (timestamp, lat, lon)
_GEOIP_TTL = 3600  # 1 hour

def _geoip_lookup(ip: str):
    """Look up lat/lon for an IP address using ip-api.com. Returns (lat, lon) or (None, None).
    Results are cached by /24 subnet for 1 hour to minimise external calls."""
    if not ip or ip.startswith("127.") or ip.startswith("10.") or ip == "::1":
        return None, None
    # Cache key: first 3 octets of IPv4
    parts = ip.split(".")
    cache_key = ".".join(parts[:3]) if len(parts) == 4 else ip
    cached = _geoip_cache.get(cache_key)
    if cached:
        ts, lat, lon = cached
        if time.time() - ts < _GEOIP_TTL:
            return lat, lon
    try:
        resp = _requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,lat,lon",
            timeout=2,
        )
        data = resp.json()
        if data.get("status") == "success":
            lat, lon = float(data["lat"]), float(data["lon"])
            _geoip_cache[cache_key] = (time.time(), lat, lon)
            return lat, lon
    except Exception:
        pass
    return None, None


# ──────────────────────────────────────────────────────────────────────
# Shared helpers (previously duplicated per handler)
# ──────────────────────────────────────────────────────────────────────

def fetch_all_rows(query_builder, page_size=1000):
    """Paginate through a Supabase query to fetch all rows."""
    all_data = []
    offset = 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        all_data.extend(res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    return all_data


def parse_weight_lbs(weight_str):
    if not weight_str:
        return 0.0
    match = re.search(r'(\d+(?:\.\d+)?)', weight_str)
    if not match:
        return 0.0
    try:
        val = float(match.group(1))
        if "kg" in weight_str.lower():
            val = val * 2.20462
        return val
    except ValueError:
        return 0.0


def classify_age_group(age_str):
    if not age_str:
        return "any"
    age_str = age_str.lower()
    years = 0
    months = 0
    matches = re.findall(r'(\d+)\s*(year|month|week|day)', age_str)
    for val_str, unit in matches:
        val = int(val_str)
        if "year" in unit:
            years = val
        elif "month" in unit:
            months = val
    if years == 0 and months > 0:
        return "puppy"
    elif years == 0:
        return "puppy"
    elif years < 1:
        return "puppy"
    elif years <= 3:
        return "young"
    elif years < 8:
        return "adult"
    else:
        return "senior"


def matches_gender(dog_gender, pref_gender):
    if not pref_gender or pref_gender == "any":
        return True
    if not dog_gender:
        return False
    dog_gender = dog_gender.lower().strip()
    pref_gender = pref_gender.lower().strip()
    if pref_gender == "male":
        return "female" not in dog_gender and "male" in dog_gender
    return pref_gender in dog_gender


# ──────────────────────────────────────────────────────────────────────
# POST /api/chat
# ──────────────────────────────────────────────────────────────────────

CHAT_MODEL = "gpt-5.4-mini"


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
        fetch = sb.table("chat_conversations") \
            .select("id") \
            .eq("email", email) \
            .eq("animal_id", animal_id) \
            .limit(1).execute()
        return fetch.data[0]["id"] if fetch.data else None
    except Exception:
        return None


def _save_messages(sb, conversation_id, user_message, assistant_reply, ip_address="", location="", sugg_prompts=None, chosen_prompt=None):
    """Append user + assistant messages to chat_messages."""
    try:
        user_row = {"conversation_id": conversation_id, "role": "user", "content": user_message, "ip_address": ip_address, "location": location}
        if sugg_prompts is not None:
            user_row["sugg_prompts"] = sugg_prompts
        if chosen_prompt is not None:
            user_row["chosen_prompt"] = chosen_prompt
        sb.table("chat_messages").insert([
            user_row,
            {"conversation_id": conversation_id, "role": "assistant", "content": assistant_reply, "ip_address": ip_address, "location": location},
        ]).execute()
    except Exception:
        pass  # Non-blocking


@router.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()

        animal_id = body.get("animal_id")
        user_message = body.get("message", "")
        conversation_history = body.get("conversation_history", [])
        user_email = (body.get("email") or "").strip().lower()
        if not user_email or user_email.endswith("@guest.chattyhound.com"):
            user_email = "anonymous@chattyhound.com"

        dog_name = body.get("dog_name") or ""
        dog_image_url = body.get("dog_image_url") or ""

        # IP/Location from forwarded headers (Railway sets x-forwarded-for)
        ip_address = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip") or ""
        # No Vercel-specific geo headers on Railway — location comes from client
        city = request.headers.get("x-vercel-ip-city")
        country = request.headers.get("x-vercel-ip-country")
        location = f"{city}, {country}" if city and country else (city or country or "")

        sugg_prompts = body.get("sugg_prompts")
        chosen_prompt = body.get("chosen_prompt")

        if not animal_id or not user_message:
            return JSONResponse(status_code=400, content={"error": "animal_id and message are required."})

        sb_client = get_supabase_client()
        res = sb_client.table("system_prompts_v2").select("system_prompt").eq("animal_id", animal_id).order("created_at", desc=True).limit(1).execute()

        if not res.data:
            return JSONResponse(status_code=404, content={"error": "System prompt not found for this dog."})

        system_prompt = res.data[0]["system_prompt"]

        input_messages = [{"role": "developer", "content": system_prompt}]
        for turn in conversation_history:
            if "role" in turn and "content" in turn:
                input_messages.append({"role": turn["role"], "content": turn["content"]})
        input_messages.append({"role": "user", "content": user_message})

        from openai import OpenAI
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        try:
            response = openai_client.chat.completions.create(model=CHAT_MODEL, messages=input_messages)
            output_text = response.choices[0].message.content
        except AttributeError:
            response = openai_client.responses.create(model=CHAT_MODEL, input=input_messages)
            output_text = response.output_text

        # Persist conversation (non-blocking)
        try:
            conv_id = _upsert_conversation(sb_client, user_email, animal_id, dog_name, dog_image_url, output_text[:200], ip_address, location)
            if conv_id:
                _save_messages(sb_client, conv_id, user_message, output_text, ip_address, location, sugg_prompts, chosen_prompt)
        except Exception:
            import traceback
            traceback.print_exc()

        return JSONResponse(content={"reply": output_text})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/random_dog
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/random_dog")
async def random_dog(request: Request):
    try:
        params = request.query_params
        viewed_str = params.get("viewed", "")
        viewed_list = [aid.strip() for aid in viewed_str.split(",") if aid.strip()]
        viewed_ids = set(viewed_list)
        email = (params.get("email") or "").strip().lower()
        animal_id_override = (params.get("animal_id") or "").strip() or None

        client = get_supabase_client()
        image_base_url = get_image_base_url()

        # ── Direct lookup by animal_id (for Saved Dogs / Resume Chat) ──
        if animal_id_override:
            active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight").eq("animal_id", animal_id_override).limit(1).execute()
            prompts_res = client.table("system_prompts_v2").select("animal_id").eq("animal_id", animal_id_override).limit(1).execute()
            profile_res = client.table("animals").select("*").eq("animal_id", animal_id_override).limit(1).execute()
            fact_res = client.table("animal_fact_profiles").select("dog_name, breed_or_description, intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, strengths_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb, info_refreshed_at, sex, age_bucket, weight_class, altered_status, age_summary, weight_summary, sugg_specific").eq("animal_id", animal_id_override).limit(1).execute()

            if not active_res.data or not profile_res.data:
                return JSONResponse(status_code=404, content={"error": "Dog not found."})
            active_dog = active_res.data[0]
            profile = profile_res.data[0]

            facts_data = fact_res.data[0] if fact_res.data else {}
            profile["name"] = facts_data.get("dog_name") or active_dog.get("name") or "Unknown"
            profile["gender"] = active_dog.get("gender") or "Unknown"
            profile["intro_summary"] = facts_data.get("intro_summary")
            profile["important_facts"] = facts_data.get("important_facts_jsonb", [])
            profile["bio"] = facts_data.get("backstory_summary", profile.get("bio", ""))
            profile["risk_flags"] = facts_data.get("risk_flags_jsonb", [])
            profile["strengths"] = facts_data.get("strengths_jsonb", [])
            profile["challenges"] = facts_data.get("challenges_jsonb", [])
            profile["ideal_home"] = facts_data.get("ideal_home_jsonb", [])
            profile["other_animals_notes"] = facts_data.get("other_animals_notes")
            profile["people_notes"] = facts_data.get("people_notes")
            profile["containment_notes"] = facts_data.get("containment_notes")
            profile["medical_notes"] = facts_data.get("medical_notes")
            profile["adoption_process_notes"] = facts_data.get("adoption_process_notes")
            profile["unknowns"] = facts_data.get("unknowns_jsonb", [])
            profile["info_refreshed_at"] = facts_data.get("info_refreshed_at")
            profile["sex"] = facts_data.get("sex", active_dog.get("gender"))
            profile["age_summary"] = facts_data.get("age_summary")
            profile["weight_summary"] = facts_data.get("weight_summary")
            profile["age_bucket"] = facts_data.get("age_bucket")
            profile["weight_class"] = facts_data.get("weight_class")
            profile["altered_status"] = facts_data.get("altered_status")
            profile["breed_or_description"] = facts_data.get("breed_or_description") or "Rescue Mix"
            profile["sugg_specific"] = facts_data.get("sugg_specific", [])

            profile["preferences_matched"] = False
            profile["user_has_preferences"] = False
            profile["match_details"] = {}
            for key in ["id", "record_hash", "created_at", "last_scrape_run_id"]:
                profile.pop(key, None)
            profile["image_base_url"] = image_base_url
            return JSONResponse(content=profile)

        # Parse user coordinates from query params for proximity matching
        user_lat = None
        user_lon = None
        try:
            lat_str = (params.get("lat") or "").strip()
            lon_str = (params.get("lon") or "").strip()
            if lat_str and lon_str:
                user_lat = float(lat_str)
                user_lon = float(lon_str)
        except Exception:
            pass

        # Fallback: server-side IP geolocation when client didn't send coords
        if user_lat is None or user_lon is None:
            client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
                        request.headers.get("x-real-ip", "") or \
                        (request.client.host if request.client else "")
            geo_lat, geo_lon = _geoip_lookup(client_ip)
            if geo_lat is not None:
                user_lat, user_lon = geo_lat, geo_lon

        closer_region = None
        if user_lat is not None and user_lon is not None:
            locations = {
                "TUCSON": (32.2226, -110.9747),
                "CHICAGO": (41.8781, -87.6298),
                "NYC": (40.7128, -74.0060),
                "LOS ANGELES": (34.0522, -118.2437),
                "HOUSTON": (29.7604, -95.3698)
            }
            min_dist = float('inf')
            for region, (lat, lon) in locations.items():
                dist = (user_lat - lat)**2 + (user_lon - lon)**2
                if dist < min_dist:
                    min_dist = dist
                    closer_region = region

        # Fetch all dog IDs, names, and filterable fields from active_dogs
        active_data = fetch_all_rows(client.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id"))
        if not active_data:
            return JSONResponse(status_code=404, content={"error": "No dogs found in active_dogs."})

        active_dogs = {row["animal_id"]: row for row in active_data}

        # Fetch shelters
        shelters_res = client.table("shelters").select("*").execute()
        shelters_map = {s["shelter_id"]: s for s in shelters_res.data} if shelters_res.data else {}

        # Fetch from animal_persona_profiles to get archetype data and freshness
        persona_data_list = fetch_all_rows(client.table("animal_persona_profiles").select("animal_id, primary_archetype_key, updated_at"))
        persona_data = {row["animal_id"]: row for row in persona_data_list}

        # Fetch animal_fact_profiles to get age_bucket and weight_class
        fact_data_list = fetch_all_rows(client.table("animal_fact_profiles").select("animal_id, age_bucket, weight_class"))
        for row in fact_data_list:
            if row["animal_id"] in active_dogs:
                active_dogs[row["animal_id"]]["age_bucket"] = row.get("age_bucket")
                active_dogs[row["animal_id"]]["weight_class"] = row.get("weight_class")

        # Fetch system_prompts_v2 to ensure only dogs with a prompt template are served
        prompts_data_list = fetch_all_rows(client.table("system_prompts_v2").select("animal_id"))
        prompt_ids = {row["animal_id"] for row in prompts_data_list}

        # Intersect: dog must be active, have a persona, AND have a prompt template
        valid_ids = list(set(active_dogs.keys()) & set(persona_data.keys()) & prompt_ids)

        if not valid_ids:
            return JSONResponse(status_code=404, content={"error": "No dogs with generated personas found."})

        # Determine last 2 unique archetypes the user has seen
        last_2_archetypes = set()
        for aid in reversed(viewed_list):
            if aid in persona_data:
                arch = persona_data[aid].get("primary_archetype_key")
                if arch:
                    last_2_archetypes.add(arch)
            if len(last_2_archetypes) >= 2:
                break

        # Fetch user preferences if logged in
        preferences = None
        has_real_preferences = False
        if email:
            pref_res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()
            if pref_res.data:
                preferences = pref_res.data[0]
                has_real_preferences = True

        if not preferences:
            preferences = {}

        q_gender = (params.get("gender") or "").strip().lower()
        q_age = (params.get("age_group") or "").strip().lower()
        q_size = (params.get("size") or "").strip().lower()
        q_location = (params.get("location") or "").strip()

        if q_gender: preferences["gender"] = q_gender; has_real_preferences = True
        if q_age: preferences["age_group"] = q_age; has_real_preferences = True
        if q_size: preferences["size"] = q_size; has_real_preferences = True
        if q_location: preferences["location"] = q_location; has_real_preferences = True

        for k in ["gender", "age_group", "size", "location"]:
            if not preferences.get(k):
                preferences[k] = "any"

        # Apply preferences filtering
        preferences_matched = False
        best_match_details = {}
        scored_dogs = {aid: 0 for aid in valid_ids}
        preferences_configured = False

        pref_gender = preferences.get("gender") or "any"
        pref_age = preferences.get("age_group") or "any"
        pref_size = preferences.get("size") or "any"
        pref_location = preferences.get("location") or "any"

        def clean_loc(s):
            return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

        if pref_location == "any":
            pass  # include all locations
        else:
            new_valid_ids = []
            for aid in valid_ids:
                dog_loc = shelters_map.get(active_dogs[aid].get("shelter_id"), {}).get("location_display_name", "")
                if clean_loc(pref_location) == clean_loc(dog_loc):
                    new_valid_ids.append(aid)
            if new_valid_ids:
                valid_ids = new_valid_ids

        has_gender = (pref_gender != "any")
        has_age = (pref_age != "any")
        has_size = (pref_size != "any")
        has_location = (pref_location != "any")
        total_pref_count = sum([has_gender, has_age, has_size, has_location])

        if total_pref_count > 0:
            preferences_configured = True
            for aid in valid_ids:
                dog = active_dogs[aid]
                score = 0
                details = {
                    "gender": {"active": has_gender, "preferred": pref_gender, "actual": dog.get("gender") or "Unknown", "matched": False},
                    "age": {"active": has_age, "preferred": pref_age, "actual": dog.get("age") or "Unknown", "matched": False},
                    "size": {"active": has_size, "preferred": pref_size, "actual": dog.get("weight") or "Unknown", "matched": False},
                    "location": {"active": has_location, "preferred": pref_location, "actual": shelters_map.get(dog.get("shelter_id"), {}).get("location_display_name", "Unknown"), "matched": False}
                }
                if has_gender:
                    if matches_gender(dog.get("gender"), pref_gender):
                        score += 1
                        details["gender"]["matched"] = True
                if has_age:
                    dog_age_group = dog.get("age_bucket") or "N/A"
                    if pref_age.lower() in dog_age_group.lower() and dog_age_group != "N/A":
                        score += 1
                        details["age"]["matched"] = True
                    details["age"]["actual"] = dog_age_group
                if has_size:
                    dog_size_class = dog.get("weight_class") or "N/A"
                    if pref_size.lower() in dog_size_class.lower() and dog_size_class != "N/A":
                        score += 1
                        details["size"]["matched"] = True
                    details["size"]["actual"] = dog_size_class
                if has_location:
                    dog_loc = shelters_map.get(dog.get("shelter_id"), {}).get("location_display_name", "")
                    if pref_location.lower() == dog_loc.lower():
                        score += 1
                        details["location"]["matched"] = True
                else:
                    dog_city = shelters_map.get(dog.get("shelter_id"), {}).get("city", "").upper()
                    if closer_region and dog_city == closer_region:
                        score += 0.8
                dog_arch = persona_data[aid].get("primary_archetype_key")
                if dog_arch and dog_arch not in last_2_archetypes:
                    score += 0.5
                scored_dogs[aid] = score
                best_match_details[aid] = details
        else:
            for aid in valid_ids:
                score = 0
                dog = active_dogs[aid]
                dog_city = shelters_map.get(dog.get("shelter_id"), {}).get("city", "").upper()
                if closer_region and dog_city == closer_region:
                    score += 0.8
                dog_arch = persona_data[aid].get("primary_archetype_key")
                if dog_arch and dog_arch not in last_2_archetypes:
                    score += 0.5
                scored_dogs[aid] = score

        # Categorize all valid dogs by freshness
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        fresh_status = {}
        for aid in valid_ids:
            dt_str = persona_data[aid].get("updated_at", "")
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
            try:
                updated_at = datetime.fromisoformat(dt_str)
                fresh_status[aid] = (updated_at >= three_days_ago)
            except Exception:
                fresh_status[aid] = True

        # Separate candidates into unviewed and viewed
        unviewed_ids = [aid for aid in valid_ids if aid not in viewed_ids]

        def select_weighted_dog(candidates):
            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0]
            try:
                res = client.table("animals").select("animal_id, bio").in_("animal_id", candidates).execute()
                lengths = {}
                for row in res.data:
                    b_len = len(row.get("bio") or "")
                    lengths[row["animal_id"]] = b_len
                weights = []
                for cid in candidates:
                    w = min(lengths.get(cid, 0), 800) / 10.0 + 10
                    weights.append(w)
                return random.choices(candidates, weights=weights, k=1)[0]
            except Exception:
                return random.choice(candidates)

        random_id = None
        if unviewed_ids:
            max_unviewed_score = max(scored_dogs[aid] for aid in unviewed_ids)
            best_unviewed_candidates = [aid for aid in unviewed_ids if scored_dogs[aid] == max_unviewed_score]
            unviewed_fresh = [aid for aid in best_unviewed_candidates if fresh_status[aid]]
            unviewed_stale = [aid for aid in best_unviewed_candidates if not fresh_status[aid]]
            if unviewed_fresh:
                random_id = select_weighted_dog(unviewed_fresh)
            else:
                random_id = select_weighted_dog(unviewed_stale)
        else:
            max_score = max(scored_dogs.values()) if scored_dogs else 0
            best_candidates = [aid for aid, score in scored_dogs.items() if score == max_score]
            all_fresh = [aid for aid in best_candidates if fresh_status[aid]]
            all_stale = [aid for aid in best_candidates if not fresh_status[aid]]
            if all_fresh:
                random_id = select_weighted_dog(all_fresh)
            else:
                random_id = select_weighted_dog(all_stale)

        # Determine whether preferences are matched for the selected dog
        if preferences_configured and random_id:
            max_overall_score = max(scored_dogs.values()) if scored_dogs else 0
            preferences_matched = (scored_dogs[random_id] >= 1.0 and (scored_dogs[random_id] == max_overall_score or scored_dogs[random_id] >= 1.0))

        # Fetch the full profile
        profile_res = client.table("animals").select("*").eq("animal_id", random_id).limit(1).execute()
        if not profile_res.data:
            return JSONResponse(status_code=404, content={"error": "Profile not found in animals table."})

        profile = profile_res.data[0]

        # Add the name, gender and facts
        fact_res = client.table("animal_fact_profiles").select("dog_name, breed_or_description, intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, strengths_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb, info_refreshed_at, sex, age_bucket, weight_class, altered_status, age_summary, weight_summary, sugg_specific").eq("animal_id", random_id).limit(1).execute()
        facts_data = fact_res.data[0] if fact_res.data else {}

        profile["name"] = facts_data.get("dog_name") or active_dogs[random_id].get("name") or "Unknown"
        profile["gender"] = active_dogs[random_id].get("gender") or "Unknown"
        profile["intro_summary"] = facts_data.get("intro_summary")
        profile["important_facts"] = facts_data.get("important_facts_jsonb", [])
        profile["bio"] = facts_data.get("backstory_summary", profile.get("bio", ""))
        profile["risk_flags"] = facts_data.get("risk_flags_jsonb", [])
        profile["strengths"] = facts_data.get("strengths_jsonb", [])
        profile["challenges"] = facts_data.get("challenges_jsonb", [])
        profile["ideal_home"] = facts_data.get("ideal_home_jsonb", [])
        profile["other_animals_notes"] = facts_data.get("other_animals_notes")
        profile["people_notes"] = facts_data.get("people_notes")
        profile["containment_notes"] = facts_data.get("containment_notes")
        profile["medical_notes"] = facts_data.get("medical_notes")
        profile["adoption_process_notes"] = facts_data.get("adoption_process_notes")
        profile["unknowns"] = facts_data.get("unknowns_jsonb", [])
        profile["info_refreshed_at"] = facts_data.get("info_refreshed_at")
        profile["sex"] = facts_data.get("sex", active_dogs[random_id].get("gender"))
        profile["age_summary"] = facts_data.get("age_summary")
        profile["weight_summary"] = facts_data.get("weight_summary")
        profile["age_bucket"] = facts_data.get("age_bucket")
        profile["weight_class"] = facts_data.get("weight_class")
        profile["altered_status"] = facts_data.get("altered_status")
        profile["breed_or_description"] = facts_data.get("breed_or_description") or "Rescue Mix"
        profile["sugg_specific"] = facts_data.get("sugg_specific", [])
        profile["preferences_matched"] = preferences_matched
        profile["user_has_preferences"] = has_real_preferences
        profile["match_details"] = best_match_details.get(random_id, {})

        suggested_location = None
        if closer_region and not has_real_preferences:
            for s in shelters_map.values():
                if s.get("city", "").upper() == closer_region:
                    suggested_location = s.get("location_display_name")
                    break
        profile["suggested_location"] = suggested_location

        for key in ["id", "record_hash", "created_at", "last_scrape_run_id"]:
            profile.pop(key, None)

        profile["image_base_url"] = image_base_url

        return JSONResponse(content=profile)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET/POST /api/favorites
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/favorites")
async def get_favorites(request: Request):
    try:
        email = (request.query_params.get("email") or "").strip()
        if not email:
            return JSONResponse(status_code=400, content={"error": "email is required"})

        sb = get_supabase_client()
        res = sb.table("saved_dogs").select("animal_id, created_at").eq("email", email).order("created_at", desc=True).execute()
        saved_records = res.data or []

        if not saved_records:
            return JSONResponse(content={"saved": []})

        animal_ids = [r["animal_id"] for r in saved_records]

        active_res = sb.table("active_dogs").select("animal_id, name, gender, age, weight").in_("animal_id", animal_ids).execute()
        active_map = {p["animal_id"]: p for p in (active_res.data or [])}

        animals_res = sb.table("animals").select("animal_id, shelter_name, shelter_profile_url, image_file, image_public_url, shelter_image_url").in_("animal_id", animal_ids).execute()
        animals_map = {a["animal_id"]: a for a in (animals_res.data or [])}

        image_base = get_image_base_url()
        saved_dogs_rich = []

        for r in saved_records:
            aid = r["animal_id"]
            active_dog = active_map.get(aid, {})
            animal = animals_map.get(aid, {})

            dog_image_url = ""
            if animal.get("image_file"):
                dog_image_url = image_base + animal["image_file"]
            elif animal.get("image_public_url"):
                dog_image_url = animal["image_public_url"]
            elif animal.get("shelter_image_url"):
                dog_image_url = animal["shelter_image_url"]

            saved_dogs_rich.append({
                "animal_id": aid,
                "created_at": r["created_at"],
                "dog_name": active_dog.get("name") or "Shelter Pup",
                "gender": active_dog.get("gender") or "Unknown",
                "age": active_dog.get("age") or "Unknown",
                "weight": active_dog.get("weight") or "Unknown",
                "shelter_name": animal.get("shelter_name") or "Pima Animal Care Center",
                "shelter_profile_url": animal.get("shelter_profile_url") or "",
                "dog_image_url": dog_image_url
            })

        return JSONResponse(content={"saved": saved_dogs_rich})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/favorites")
async def post_favorites(request: Request):
    try:
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        animal_id = (body.get("animal_id") or "").strip()
        action = body.get("action", "save")

        if not email or not animal_id:
            return JSONResponse(status_code=400, content={"error": "email and animal_id are required"})

        sb = get_supabase_client()

        if action == "remove":
            sb.table("saved_dogs").delete().eq("email", email).eq("animal_id", animal_id).execute()
            return JSONResponse(content={"status": "removed"})
        else:
            dog_name = body.get("dog_name") or ""
            dog_image_url = body.get("dog_image_url") or ""
            row = {"email": email, "animal_id": animal_id, "dog_name": dog_name, "dog_image_url": dog_image_url}
            sb.table("saved_dogs").upsert(row, on_conflict="email,animal_id").execute()
            return JSONResponse(content={"status": "saved"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# POST /api/login
# ──────────────────────────────────────────────────────────────────────

@router.post("/api/login")
async def login(request: Request):
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        if not email:
            return JSONResponse(status_code=400, content={"error": "Email is required."})

        client = get_supabase_client()
        res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()

        if res.data:
            profile = res.data[0]
        else:
            new_profile = {"email": email, "gender": "any", "age_group": "any", "size": "any", "location": "any"}
            insert_res = client.table("user_preferences").insert(new_profile).execute()
            if not insert_res.data:
                return JSONResponse(status_code=500, content={"error": "Failed to create user profile."})
            profile = insert_res.data[0]

        return JSONResponse(content=profile)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# POST /api/save_preferences
# ──────────────────────────────────────────────────────────────────────

@router.post("/api/save_preferences")
async def save_preferences(request: Request):
    try:
        body = await request.json()

        pref_obj = body.get("preferences", body)
        email = body.get("email", "").strip().lower()
        gender = pref_obj.get("gender", "any").strip().lower()
        age_group = pref_obj.get("age_group", "any").strip().lower()
        size = pref_obj.get("size", "any").strip().lower()
        location = pref_obj.get("location", "any").strip()

        if not email:
            return JSONResponse(status_code=400, content={"error": "Email is required."})

        client = get_supabase_client()

        valid_genders = {"male", "female", "any"}
        valid_ages = {"puppy", "young", "adult", "senior", "any"}
        valid_sizes = {"small", "medium", "large", "any"}

        shelters_res = client.table("shelters").select("location_display_name").execute()
        valid_locations = set([s["location_display_name"] for s in shelters_res.data]) if shelters_res.data else set()
        valid_locations.add("any")

        if gender not in valid_genders: gender = "any"
        if age_group not in valid_ages: age_group = "any"
        if size not in valid_sizes: size = "any"
        if location not in valid_locations: location = "any"

        pref_data = {
            "email": email,
            "gender": gender,
            "age_group": age_group,
            "size": size,
            "location": location,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        upsert_res = client.table("user_preferences").upsert(pref_data, on_conflict="email").execute()
        if not upsert_res.data:
            return JSONResponse(status_code=500, content={"error": "Failed to save user preferences."})

        return JSONResponse(content={"ok": True, "preferences": upsert_res.data[0]})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/chat_history
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/chat_history")
async def chat_history(request: Request):
    try:
        params = request.query_params
        email = params.get("email")
        animal_id = params.get("animal_id")

        if not email:
            return JSONResponse(status_code=400, content={"error": "email is required"})

        sb = get_supabase_client()

        if animal_id:
            conv_res = sb.table("chat_conversations").select("id").eq("email", email).eq("animal_id", animal_id).limit(1).execute()
            if not conv_res.data:
                return JSONResponse(content={"messages": [], "conversation_id": None})

            conv_id = conv_res.data[0]["id"]
            msg_res = sb.table("chat_messages").select("role, content, created_at").eq("conversation_id", conv_id).order("created_at", desc=False).execute()

            return JSONResponse(content={"conversation_id": conv_id, "messages": msg_res.data or []})
        else:
            conv_res = sb.table("chat_conversations") \
                .select("animal_id, dog_name, dog_image_url, last_message_preview, updated_at") \
                .eq("email", email).order("updated_at", desc=True).limit(20).execute()

            return JSONResponse(content={"conversations": conv_res.data or []})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/locations
# ──────────────────────────────────────────────────────────────────────

# Beta location restriction
BETA_SHELTER_IDS = set()
BETA_ALLOWED_EMAILS = {"reedr1208@gmail.com"}


@router.get("/api/locations")
async def locations(request: Request):
    try:
        client = get_supabase_client()

        user_email = (request.query_params.get("email") or "").strip().lower()
        is_beta_user = user_email in BETA_ALLOWED_EMAILS

        res = client.table("shelters").select("shelter_id, location_display_name, relative_path").execute()

        locations_map = {}
        for row in res.data:
            shelter_id = row.get("shelter_id", "")
            disp = row.get("location_display_name")
            if not disp:
                continue
            if shelter_id in BETA_SHELTER_IDS and not is_beta_user:
                continue
            if disp not in locations_map:
                locations_map[disp] = {"display_name": disp, "relative_path": row.get("relative_path") or "", "shelter_ids": []}
            locations_map[disp]["shelter_ids"].append(shelter_id)

        locations_list = sorted(locations_map.values(), key=lambda x: x["display_name"])
        return JSONResponse(content={"locations": locations_list})

    except Exception as e:
        logger.error(f"Error fetching locations: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/suggested_prompts
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/suggested_prompts")
async def suggested_prompts(request: Request):
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

        return JSONResponse(content={"informative": informative, "whimsical": whimsical})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# POST /api/delete_account
# ──────────────────────────────────────────────────────────────────────

@router.post("/api/delete_account")
async def delete_account(request: Request):
    try:
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        if not email:
            return JSONResponse(status_code=400, content={"error": "email is required"})

        sb = get_supabase_client()

        # 1) chat_messages — referenced by conversation_id
        convo_res = sb.table("chat_conversations").select("id").eq("email", email).execute()
        convo_ids = [c["id"] for c in (convo_res.data or []) if c.get("id") is not None]
        if convo_ids:
            sb.table("chat_messages").delete().in_("conversation_id", convo_ids).execute()

        # 2) conversations, 3) saved dogs, 4) preferences
        sb.table("chat_conversations").delete().eq("email", email).execute()
        sb.table("saved_dogs").delete().eq("email", email).execute()
        sb.table("user_preferences").delete().eq("email", email).execute()

        return JSONResponse(content={"status": "deleted"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
