"""
FastAPI routes for all BarkBot JSON API endpoints.
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from routes.deps import get_supabase_client, get_image_base_url
from routes.dog_ranking import apply_hard_filters, score_candidates, select_dog

router = APIRouter()
logger = logging.getLogger("barkbot.api")


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

CHAT_MODEL = "gpt-5.6-luna"


def _ensure_user_preferences(sb, email):
    """Ensure a user_preferences row exists for the given email (FK requirement)."""
    try:
        sb.table("user_preferences").upsert({"email": email}, on_conflict="email").execute()
    except Exception:
        pass  # Non-blocking — row may already exist


def _upsert_conversation(sb, email, animal_id, dog_name, dog_image_url, last_preview):
    """Upsert a chat_conversations row and return the conversation id."""
    try:
        _ensure_user_preferences(sb, email)
        row = {
            "email": email,
            "animal_id": animal_id,
            "dog_name": dog_name or "",
            "dog_image_url": dog_image_url or "",
            "last_message_preview": last_preview[:200] if last_preview else "",
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


def _save_messages(sb, conversation_id, user_message, assistant_reply, sugg_prompts=None, chosen_prompt=None):
    """Append user + assistant messages to chat_messages."""
    try:
        user_row = {"conversation_id": conversation_id, "role": "user", "content": user_message}
        if sugg_prompts is not None:
            user_row["sugg_prompts"] = sugg_prompts
        if chosen_prompt is not None:
            user_row["chosen_prompt"] = chosen_prompt
        sb.table("chat_messages").insert([
            user_row,
            {"conversation_id": conversation_id, "role": "assistant", "content": assistant_reply},
        ]).execute()
    except Exception:
        pass  # Non-blocking

# ── Chat rate limiting ──────────────────────────────────────────────
_chat_rate_store: dict[str, list[float]] = {}
_CHAT_RATE_LIMIT = 20  # max requests per window
_CHAT_RATE_WINDOW = 60  # seconds


def _chat_is_rate_limited(ip: str) -> bool:
    now = time.time()
    timestamps = _chat_rate_store.get(ip, [])
    timestamps = [t for t in timestamps if now - t < _CHAT_RATE_WINDOW]
    _chat_rate_store[ip] = timestamps
    if len(timestamps) >= _CHAT_RATE_LIMIT:
        return True
    timestamps.append(now)
    return False


@router.post("/api/chat")
async def chat(request: Request):
    try:
        # Rate limit by IP
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else "unknown"
        if _chat_is_rate_limited(ip):
            return JSONResponse(status_code=429, content={"error": "Too many messages. Please wait a moment and try again."})

        body = await request.json()

        animal_id = body.get("animal_id")
        user_message = body.get("message", "")
        conversation_history = body.get("conversation_history", [])
        user_email = (body.get("email") or "").strip().lower()
        if not user_email:
            user_email = "anonymous@chattyhound.com"

        dog_name = body.get("dog_name") or ""
        dog_image_url = body.get("dog_image_url") or ""

        # IP/Location — used only ephemerally for rate-limiting, NOT stored
        # (geo headers come from Railway reverse proxy if configured)

        sugg_prompts = body.get("sugg_prompts")
        chosen_prompt = body.get("chosen_prompt")

        if not animal_id or not user_message:
            return JSONResponse(status_code=400, content={"error": "animal_id and message are required."})

        # ── Server-side input validation (abuse controls) ──
        MAX_MESSAGE_LENGTH = 2000
        MAX_HISTORY_TURNS = 50
        if len(user_message) > MAX_MESSAGE_LENGTH:
            return JSONResponse(status_code=400, content={"error": f"Message too long (max {MAX_MESSAGE_LENGTH} characters)."})
        if len(conversation_history) > MAX_HISTORY_TURNS:
            conversation_history = conversation_history[-MAX_HISTORY_TURNS:]
        # Validate history entries have valid roles
        valid_roles = {"user", "assistant"}
        conversation_history = [t for t in conversation_history if isinstance(t, dict) and t.get("role") in valid_roles and isinstance(t.get("content"), str)]

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
            response = openai_client.chat.completions.create(model=CHAT_MODEL, messages=input_messages, max_completion_tokens=1024)
            output_text = response.choices[0].message.content
        except AttributeError:
            response = openai_client.responses.create(model=CHAT_MODEL, input=input_messages)
            output_text = response.output_text

        # Persist conversation (non-blocking) — skip if user disabled retention
        try:
            # Check retention preference
            _skip_save = False
            try:
                pref_res = sb_client.table("user_preferences").select("chat_retention").eq("email", user_email).limit(1).execute()
                if pref_res.data and pref_res.data[0].get("chat_retention") is False:
                    _skip_save = True
            except Exception:
                pass

            if not _skip_save:
                conv_id = _upsert_conversation(sb_client, user_email, animal_id, dog_name, dog_image_url, output_text[:200])
                if conv_id:
                    _save_messages(sb_client, conv_id, user_message, output_text, sugg_prompts, chosen_prompt)
        except Exception:
            import traceback
            traceback.print_exc()

        return JSONResponse(content={"reply": output_text})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/search_dogs — lightweight list for client-side name search
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/search_dogs")
async def search_dogs():
    """Return all chat-eligible dogs for client-side name search."""
    try:
        client = get_supabase_client()
        image_base_url = get_image_base_url()

        active_list = fetch_all_rows(
            client.table("active_dogs").select("animal_id, name, shelter_id")
        )
        active_map = {r["animal_id"]: r for r in active_list}

        persona_list = fetch_all_rows(
            client.table("animal_persona_profiles").select("animal_id")
        )
        persona_ids = {r["animal_id"] for r in persona_list}

        prompt_list = fetch_all_rows(
            client.table("system_prompts_v2").select("animal_id")
        )
        prompt_ids = {r["animal_id"] for r in prompt_list}

        fact_list = fetch_all_rows(
            client.table("animal_fact_profiles").select("animal_id, dog_name")
        )
        fact_names = {r["animal_id"]: r.get("dog_name") for r in fact_list}

        shelters_res = client.table("shelters").select("shelter_id, city, state").execute()
        shelters_map = {s["shelter_id"]: s for s in shelters_res.data}

        # Fetch actual image paths from animals table
        img_list = fetch_all_rows(
            client.table("animals").select("animal_id, image_file")
        )
        img_map = {r["animal_id"]: r.get("image_file") for r in img_list}

        eligible_ids = set(active_map.keys()) & persona_ids & prompt_ids

        dogs = []
        for aid in eligible_ids:
            dog = active_map[aid]
            shelter = shelters_map.get(dog.get("shelter_id"), {})
            name = fact_names.get(aid) or dog.get("name") or "Unknown"
            img_file = img_map.get(aid)
            image_url = f"{image_base_url}{img_file}" if img_file else ""
            dogs.append({
                "id": aid,
                "name": name,
                "image_url": image_url,
                "shelter_id": dog.get("shelter_id", ""),
                "city": shelter.get("city", ""),
                "state": shelter.get("state", ""),
            })

        dogs.sort(key=lambda d: d["name"].lower())
        return JSONResponse(
            content={"dogs": dogs, "count": len(dogs)},
            headers={"Cache-Control": "public, max-age=300"},
        )

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
            active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id").eq("animal_id", animal_id_override).limit(1).execute()
            prompts_res = client.table("system_prompts_v2").select("animal_id").eq("animal_id", animal_id_override).limit(1).execute()
            profile_res = client.table("animals").select("*").eq("animal_id", animal_id_override).limit(1).execute()
            fact_res = client.table("animal_fact_profiles").select("dog_name, breed_or_description, intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb, info_refreshed_at, sex, age_bucket, weight_class, altered_status, age_summary, weight_summary, highlights").eq("animal_id", animal_id_override).limit(1).execute()

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
            profile["highlights"] = facts_data.get("highlights", [])

            profile["preferences_matched"] = False
            profile["user_has_preferences"] = False
            profile["match_details"] = {}

            # Add shelter relative_path for share URL construction
            dog_sid = active_dog.get("shelter_id", "")
            if dog_sid:
                shelter_res = client.table("shelters").select("relative_path").eq("shelter_id", dog_sid).limit(1).execute()
                profile["relative_path"] = (shelter_res.data[0].get("relative_path", "") if shelter_res.data else "")
            else:
                profile["relative_path"] = ""

            for key in ["id", "record_hash", "created_at", "last_scrape_run_id"]:
                profile.pop(key, None)
            profile["image_base_url"] = image_base_url
            return JSONResponse(content=profile)


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

        # Fetch animal_fact_profiles to get age_bucket, weight_class, and lifestyle filter fields
        fact_data_list = fetch_all_rows(client.table("animal_fact_profiles").select("animal_id, age_bucket, weight_class, altered_status, energy_level, good_with_dogs, house_trained"))
        for row in fact_data_list:
            if row["animal_id"] in active_dogs:
                active_dogs[row["animal_id"]]["age_bucket"] = row.get("age_bucket")
                active_dogs[row["animal_id"]]["weight_class"] = row.get("weight_class")
                active_dogs[row["animal_id"]]["altered_status"] = row.get("altered_status")
                active_dogs[row["animal_id"]]["energy_level"] = row.get("energy_level")
                active_dogs[row["animal_id"]]["good_with_dogs"] = row.get("good_with_dogs")
                active_dogs[row["animal_id"]]["house_trained"] = row.get("house_trained")

        # Fetch system_prompts_v2 to ensure only dogs with a prompt template are served
        prompts_data_list = fetch_all_rows(client.table("system_prompts_v2").select("animal_id"))
        prompt_ids = {row["animal_id"] for row in prompts_data_list}

        # Intersect: dog must be active, have a persona, AND have a prompt template
        valid_ids = list(set(active_dogs.keys()) & set(persona_data.keys()) & prompt_ids)

        if not valid_ids:
            return JSONResponse(status_code=404, content={"error": "No dogs with generated personas found."})

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
        q_energy = (params.get("energy") or "").strip().lower()
        q_altered = (params.get("altered") or "").strip().lower()
        q_dogs = (params.get("dogs") or "").strip().lower()
        q_house_trained = (params.get("house_trained") or "").strip().lower()

        if q_gender: preferences["gender"] = q_gender; has_real_preferences = True
        if q_age: preferences["age_group"] = q_age; has_real_preferences = True
        if q_size: preferences["size"] = q_size; has_real_preferences = True
        if q_location: preferences["location"] = q_location; has_real_preferences = True
        if q_energy: preferences["energy"] = q_energy; has_real_preferences = True
        if q_altered: preferences["altered"] = q_altered; has_real_preferences = True
        if q_dogs == "true": preferences["dogs"] = True; has_real_preferences = True
        if q_house_trained == "true": preferences["house_trained"] = True; has_real_preferences = True

        for k in ["gender", "age_group", "size", "location", "energy", "altered"]:
            if not preferences.get(k):
                preferences[k] = "any"
        for k in ["dogs", "house_trained"]:
            if not preferences.get(k):
                preferences[k] = False

        # ── Hard filters (delegated to dog_ranking) ───────────────────
        valid_ids = apply_hard_filters(valid_ids, active_dogs, shelters_map, preferences)

        if not valid_ids:
            return JSONResponse(status_code=404, content={"error": "No dogs match your current preferences.", "no_matches": True})

        # ── Soft scoring (delegated to dog_ranking) ───────────────────
        scored_dogs = score_candidates(valid_ids, persona_data, viewed_list, client)

        # ── Selection (delegated to dog_ranking) ──────────────────────
        random_id = select_dog(valid_ids, scored_dogs, persona_data, viewed_ids, client)

        if not random_id:
            return JSONResponse(status_code=404, content={"error": "Could not select a dog."})

        # ── Build match_details for frontend compat dots ──────────────
        preferences_matched = False
        best_match_details = {}
        pref_gender = preferences.get("gender") or "any"
        pref_age = preferences.get("age_group") or "any"
        pref_size = preferences.get("size") or "any"
        pref_location = preferences.get("location") or "any"

        has_gender = (pref_gender != "any")
        has_age = (pref_age != "any")
        has_size = (pref_size != "any")
        has_location = (pref_location not in ("any", "all"))
        preferences_configured = has_gender or has_age or has_size or has_location

        if preferences_configured:
            dog = active_dogs[random_id]
            details = {
                "gender": {"active": has_gender, "preferred": pref_gender, "actual": dog.get("gender") or "Unknown", "matched": False},
                "age": {"active": has_age, "preferred": pref_age, "actual": dog.get("age") or "Unknown", "matched": False},
                "size": {"active": has_size, "preferred": pref_size, "actual": dog.get("weight") or "Unknown", "matched": False},
                "location": {"active": has_location, "preferred": pref_location, "actual": shelters_map.get(dog.get("shelter_id"), {}).get("location_display_name", "Unknown"), "matched": False}
            }
            if has_gender and matches_gender(dog.get("gender"), pref_gender):
                details["gender"]["matched"] = True
            if has_age:
                dog_age_group = dog.get("age_bucket") or "N/A"
                if pref_age.lower() in dog_age_group.lower() and dog_age_group != "N/A":
                    details["age"]["matched"] = True
                details["age"]["actual"] = dog_age_group
            if has_size:
                dog_size_class = dog.get("weight_class") or "N/A"
                if pref_size.lower() in dog_size_class.lower() and dog_size_class != "N/A":
                    details["size"]["matched"] = True
                details["size"]["actual"] = dog_size_class
            if has_location:
                dog_loc = shelters_map.get(dog.get("shelter_id"), {}).get("location_display_name", "")
                if pref_location.lower() == dog_loc.lower():
                    details["location"]["matched"] = True
            best_match_details[random_id] = details
            preferences_matched = all(d["matched"] for d in details.values() if d["active"])

        # ── Fetch the full profile ────────────────────────────────────
        profile_res = client.table("animals").select("*").eq("animal_id", random_id).limit(1).execute()
        if not profile_res.data:
            return JSONResponse(status_code=404, content={"error": "Profile not found in animals table."})

        profile = profile_res.data[0]

        # Add the name, gender and facts
        fact_res = client.table("animal_fact_profiles").select("dog_name, breed_or_description, intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb, info_refreshed_at, sex, age_bucket, weight_class, altered_status, age_summary, weight_summary, highlights").eq("animal_id", random_id).limit(1).execute()
        facts_data = fact_res.data[0] if fact_res.data else {}

        profile["name"] = facts_data.get("dog_name") or active_dogs[random_id].get("name") or "Unknown"
        profile["gender"] = active_dogs[random_id].get("gender") or "Unknown"
        profile["intro_summary"] = facts_data.get("intro_summary")
        profile["important_facts"] = facts_data.get("important_facts_jsonb", [])
        profile["bio"] = facts_data.get("backstory_summary", profile.get("bio", ""))
        profile["risk_flags"] = facts_data.get("risk_flags_jsonb", [])
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
        profile["highlights"] = facts_data.get("highlights", [])
        profile["preferences_matched"] = preferences_matched
        profile["user_has_preferences"] = has_real_preferences
        profile["match_details"] = best_match_details.get(random_id, {})

        # Add shelter relative_path for share URL construction
        dog_shelter_id = active_dogs[random_id].get("shelter_id", "")
        profile["relative_path"] = shelters_map.get(dog_shelter_id, {}).get("relative_path", "")

        for key in ["id", "record_hash", "created_at", "last_scrape_run_id"]:
            profile.pop(key, None)

        profile["image_base_url"] = image_base_url

        return JSONResponse(content=profile)



    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/browse_dogs
# Returns all dogs matching current preferences for the tile grid view
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/browse_dogs")
async def browse_dogs(request: Request):
    try:
        params = request.query_params
        email = (params.get("email") or "").strip().lower()

        client = get_supabase_client()
        image_base_url = get_image_base_url()

        # Fetch all active dogs with filterable fields
        active_data = fetch_all_rows(client.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id"))
        if not active_data:
            return JSONResponse(content={"dogs": [], "total": 0, "image_base_url": image_base_url})

        active_dogs = {row["animal_id"]: row for row in active_data}

        # Fetch shelters
        shelters_res = client.table("shelters").select("*").execute()
        shelters_map = {s["shelter_id"]: s for s in shelters_res.data} if shelters_res.data else {}

        # Fetch persona profiles (needed to filter to dogs with personas)
        persona_data_list = fetch_all_rows(client.table("animal_persona_profiles").select("animal_id"))
        persona_ids = {row["animal_id"] for row in persona_data_list}

        # Fetch fact profiles for filtering + names
        fact_data_list = fetch_all_rows(client.table("animal_fact_profiles").select("animal_id, dog_name, age_bucket, weight_class, altered_status, energy_level, good_with_dogs, house_trained"))
        fact_map = {}
        for row in fact_data_list:
            fact_map[row["animal_id"]] = row
            if row["animal_id"] in active_dogs:
                active_dogs[row["animal_id"]]["age_bucket"] = row.get("age_bucket")
                active_dogs[row["animal_id"]]["weight_class"] = row.get("weight_class")
                active_dogs[row["animal_id"]]["altered_status"] = row.get("altered_status")
                active_dogs[row["animal_id"]]["energy_level"] = row.get("energy_level")
                active_dogs[row["animal_id"]]["good_with_dogs"] = row.get("good_with_dogs")
                active_dogs[row["animal_id"]]["house_trained"] = row.get("house_trained")

        # Fetch system_prompts_v2 to ensure only dogs with a prompt are served
        prompts_data_list = fetch_all_rows(client.table("system_prompts_v2").select("animal_id"))
        prompt_ids = {row["animal_id"] for row in prompts_data_list}

        valid_ids = list(set(active_dogs.keys()) & persona_ids & prompt_ids)

        if not valid_ids:
            return JSONResponse(content={"dogs": [], "total": 0, "image_base_url": image_base_url})

        # Build preferences from query params + stored prefs
        preferences = {}
        has_real_preferences = False
        if email:
            pref_res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()
            if pref_res.data:
                preferences = pref_res.data[0]
                has_real_preferences = True

        q_gender = (params.get("gender") or "").strip().lower()
        q_age = (params.get("age_group") or "").strip().lower()
        q_size = (params.get("size") or "").strip().lower()
        q_location = (params.get("location") or "").strip()
        q_energy = (params.get("energy") or "").strip().lower()
        q_altered = (params.get("altered") or "").strip().lower()
        q_dogs = (params.get("dogs") or "").strip().lower()
        q_house_trained = (params.get("house_trained") or "").strip().lower()

        if q_gender: preferences["gender"] = q_gender
        if q_age: preferences["age_group"] = q_age
        if q_size: preferences["size"] = q_size
        if q_location: preferences["location"] = q_location
        if q_energy: preferences["energy"] = q_energy
        if q_altered: preferences["altered"] = q_altered
        if q_dogs == "true": preferences["dogs"] = True
        if q_house_trained == "true": preferences["house_trained"] = True

        for k in ["gender", "age_group", "size", "location", "energy", "altered"]:
            if not preferences.get(k):
                preferences[k] = "any"
        for k in ["dogs", "house_trained"]:
            if not preferences.get(k):
                preferences[k] = False

        # Apply hard filters
        valid_ids = apply_hard_filters(valid_ids, active_dogs, shelters_map, preferences)

        # Fetch image data for matching dogs
        animals_res = fetch_all_rows(client.table("animals").select("animal_id, image_file, image_public_url, shelter_image_url, shelter_name"))
        animals_map = {a["animal_id"]: a for a in animals_res}

        # Build the lightweight tile list
        dogs_list = []
        for aid in valid_ids:
            active = active_dogs.get(aid, {})
            facts = fact_map.get(aid, {})
            animal = animals_map.get(aid, {})
            shelter = shelters_map.get(active.get("shelter_id", ""), {})

            img_file = animal.get("image_file")
            if img_file and image_base_url:
                image_url = image_base_url + img_file
            elif animal.get("image_public_url"):
                image_url = animal["image_public_url"]
            elif animal.get("shelter_image_url"):
                image_url = animal["shelter_image_url"]
            else:
                image_url = ""

            dogs_list.append({
                "animal_id": aid,
                "name": facts.get("dog_name") or active.get("name") or "Unknown",
                "shelter_name": animal.get("shelter_name") or shelter.get("shelter_name", ""),
                "location": shelter.get("location_display_name", ""),
                "image_url": image_url,
                "relative_path": shelter.get("relative_path", ""),
            })

        # Sort alphabetically by name
        dogs_list.sort(key=lambda d: d["name"].lower())

        return JSONResponse(content={
            "dogs": dogs_list,
            "total": len(dogs_list),
            "image_base_url": image_base_url,
        })

    except Exception as e:
        logger.exception("browse_dogs error")
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

        active_res = sb.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id").in_("animal_id", animal_ids).execute()
        active_map = {p["animal_id"]: p for p in (active_res.data or [])}

        animals_res = sb.table("animals").select("animal_id, shelter_name, shelter_profile_url, city, state, image_file, image_public_url, shelter_image_url").in_("animal_id", animal_ids).execute()
        animals_map = {a["animal_id"]: a for a in (animals_res.data or [])}

        facts_res = sb.table("animal_fact_profiles").select("animal_id, breed_or_description, age_summary").in_("animal_id", animal_ids).execute()
        facts_map = {f["animal_id"]: f for f in (facts_res.data or [])}

        # Fetch shelter relative_path for share URLs
        shelter_ids = list({active_map.get(aid, {}).get("shelter_id") for aid in animal_ids if active_map.get(aid, {}).get("shelter_id")})
        shelters_path_map = {}
        if shelter_ids:
            shelters_res = sb.table("shelters").select("shelter_id, relative_path").in_("shelter_id", shelter_ids).execute()
            shelters_path_map = {s["shelter_id"]: s.get("relative_path", "") for s in (shelters_res.data or [])}

        image_base = get_image_base_url()
        saved_dogs_rich = []

        for r in saved_records:
            aid = r["animal_id"]
            active_dog = active_map.get(aid, {})
            animal = animals_map.get(aid, {})
            facts = facts_map.get(aid, {})
            shelter_id = active_dog.get("shelter_id", "")

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
                "gender": active_dog.get("gender") or "",
                "age": active_dog.get("age") or "",
                "age_summary": facts.get("age_summary") or "",
                "weight": active_dog.get("weight") or "",
                "breed_or_description": facts.get("breed_or_description") or "",
                "shelter_name": animal.get("shelter_name") or "",
                "shelter_profile_url": animal.get("shelter_profile_url") or "",
                "city": animal.get("city") or "",
                "state": animal.get("state") or "",
                "relative_path": shelters_path_map.get(shelter_id, ""),
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
            _ensure_user_preferences(sb, email)
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
        valid_locations.add("all")

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

        # Fetch retention preference
        pref_res = sb.table("user_preferences").select("chat_retention").eq("email", email).limit(1).execute()
        chat_retention = True
        if pref_res.data and pref_res.data[0].get("chat_retention") is False:
            chat_retention = False

        if animal_id:
            conv_res = sb.table("chat_conversations").select("id").eq("email", email).eq("animal_id", animal_id).limit(1).execute()
            if not conv_res.data:
                return JSONResponse(content={"messages": [], "conversation_id": None, "chat_retention": chat_retention})

            conv_id = conv_res.data[0]["id"]
            msg_res = sb.table("chat_messages").select("role, content, created_at").eq("conversation_id", conv_id).order("created_at", desc=False).execute()

            return JSONResponse(content={"conversation_id": conv_id, "messages": msg_res.data or [], "chat_retention": chat_retention})
        else:
            conv_res = sb.table("chat_conversations") \
                .select("animal_id, dog_name, dog_image_url, last_message_preview, updated_at") \
                .eq("email", email).order("updated_at", desc=True).limit(20).execute()

            convs = conv_res.data or []

            # Annotate each conversation with availability status
            if convs:
                aids = [c["animal_id"] for c in convs]
                active_res = sb.table("active_dogs").select("animal_id").in_("animal_id", aids).execute()
                active_set = {r["animal_id"] for r in (active_res.data or [])}
                for c in convs:
                    c["is_available"] = c["animal_id"] in active_set

            return JSONResponse(content={"conversations": convs, "chat_retention": chat_retention})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/api/chat_history")
async def delete_chat_history(request: Request):
    """Delete individual conversation or all conversations for a user."""
    try:
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        animal_id = (body.get("animal_id") or "").strip()  # optional: delete specific conversation

        if not email:
            return JSONResponse(status_code=400, content={"error": "email is required"})

        sb = get_supabase_client()

        if animal_id:
            # Delete a single conversation
            conv_res = sb.table("chat_conversations").select("id").eq("email", email).eq("animal_id", animal_id).limit(1).execute()
            if conv_res.data:
                conv_id = conv_res.data[0]["id"]
                sb.table("chat_messages").delete().eq("conversation_id", conv_id).execute()
                sb.table("chat_conversations").delete().eq("id", conv_id).execute()
            return JSONResponse(content={"status": "deleted", "animal_id": animal_id})
        else:
            # Delete ALL conversations for this user
            conv_res = sb.table("chat_conversations").select("id").eq("email", email).execute()
            conv_ids = [c["id"] for c in (conv_res.data or []) if c.get("id") is not None]
            if conv_ids:
                sb.table("chat_messages").delete().in_("conversation_id", conv_ids).execute()
            sb.table("chat_conversations").delete().eq("email", email).execute()
            return JSONResponse(content={"status": "deleted_all"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/chat_retention")
async def set_chat_retention(request: Request):
    """Toggle chat retention preference for a user."""
    try:
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        retain = body.get("retain", True)  # True = keep history, False = never retain

        if not email:
            return JSONResponse(status_code=400, content={"error": "email is required"})

        sb = get_supabase_client()
        _ensure_user_preferences(sb, email)

        sb.table("user_preferences").update({
            "chat_retention": bool(retain),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("email", email).execute()

        # If disabling retention, delete all existing conversations
        if not retain:
            conv_res = sb.table("chat_conversations").select("id").eq("email", email).execute()
            conv_ids = [c["id"] for c in (conv_res.data or []) if c.get("id") is not None]
            if conv_ids:
                sb.table("chat_messages").delete().in_("conversation_id", conv_ids).execute()
            sb.table("chat_conversations").delete().eq("email", email).execute()

        return JSONResponse(content={"status": "ok", "chat_retention": bool(retain)})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# GET /api/locations
# ──────────────────────────────────────────────────────────────────────

# Beta location restriction
BETA_SHELTER_IDS = set()
_beta_emails_str = os.environ.get("BETA_ALLOWED_EMAILS", "")
BETA_ALLOWED_EMAILS = {e.strip().lower() for e in _beta_emails_str.split(",") if e.strip()}


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
# GET /api/detect_location  — IP-based location auto-detection
# ──────────────────────────────────────────────────────────────────────

# Region coordinates for nearest-shelter matching
_REGION_COORDS = {
    "Tucson, AZ": (32.2226, -110.9747),
    "Phoenix, AZ": (33.4484, -112.0740),
    "Chicago, IL": (41.8781, -87.6298),
    "New York, NY": (40.7128, -74.0060),
    "Los Angeles, CA": (34.0522, -118.2437),
    "Houston, TX": (29.7604, -95.3698),
    "San Antonio, TX": (29.4241, -98.4936),
    "Dallas, TX": (32.7767, -96.7970),
    "Philadelphia, PA": (39.9526, -75.1652),
    "San Diego, CA": (32.7157, -117.1611),
    "San Francisco, CA": (37.7749, -122.4194),
    "Jacksonville, FL": (30.3322, -81.6557),
}

import math as _math
import requests as _requests


@router.get("/api/detect_location")
async def detect_location(request: Request):
    """Return the nearest shelter location using ephemeral IP geolocation.

    Privacy note: The IP is read from request headers (standard server behavior),
    used only in-memory for this single geo lookup, and is NEVER stored in any
    database, log, or analytics system.
    """
    try:
        user_lat, user_lon = None, None

        # 1. Check for reverse-proxy geo headers first (no external call needed)
        geo_lat = request.headers.get("x-geo-ip-latitude")
        geo_lon = request.headers.get("x-geo-ip-longitude")
        if geo_lat and geo_lon:
            try:
                user_lat, user_lon = float(geo_lat), float(geo_lon)
            except (ValueError, TypeError):
                pass

        # 2. Fall back to HTTPS geo lookup using the request IP (ephemeral, not stored)
        if user_lat is None:
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or request.headers.get("x-real-ip", "")
                or (request.client.host if request.client else "")
            )
            if client_ip and not client_ip.startswith(("127.", "10.", "192.168.", "172.")) and client_ip != "::1":
                try:
                    resp = _requests.get(
                        f"https://ipapi.co/{client_ip}/json/",
                        timeout=2,
                        headers={"User-Agent": "ChattyHound/1.0"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("latitude") and data.get("longitude"):
                            user_lat, user_lon = float(data["latitude"]), float(data["longitude"])
                except Exception:
                    pass  # Non-critical — user will just pick location manually

        if user_lat is None:
            return JSONResponse(content={"location": None})

        # Fetch locations from DB
        sb = get_supabase_client()
        res = sb.table("shelters").select("shelter_id, location_display_name").execute()
        known_display_names = set()
        for row in res.data:
            dn = row.get("location_display_name")
            if dn:
                known_display_names.add(dn)

        # Find nearest region
        best_dist = float("inf")
        best_name = None
        for region_base, (lat, lon) in _REGION_COORDS.items():
            dist = (user_lat - lat) ** 2 + (user_lon - lon) ** 2
            if dist < best_dist:
                # Match region base to a known display_name (which may include emoji)
                matching = [dn for dn in known_display_names if dn.startswith(region_base)]
                if matching:
                    best_dist = dist
                    best_name = matching[0]

        return JSONResponse(content={"location": best_name})

    except Exception as e:
        logger.error(f"Error detecting location: {e}")
        return JSONResponse(content={"location": None})


# ──────────────────────────────────────────────────────────────────────
# GET /api/suggested_prompts
# ──────────────────────────────────────────────────────────────────────

@router.get("/api/suggested_prompts")
async def suggested_prompts(request: Request):
    try:
        client = get_supabase_client()
        res = client.table("suggested_prompts").select("*").execute()

        informative = []
        whimsical = []
        for row in res.data:
            entry = {"text": row["prompt_text"], "intro_point": row.get("intro_point", 1)}
            if row["category"] == "Informative":
                informative.append(entry)
            elif row["category"] == "Whimsical":
                whimsical.append(entry)

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


# ──────────────────────────────────────────────────────────────────────
# CONTACT FORM
# ──────────────────────────────────────────────────────────────────────
_contact_rate_store: dict[str, list[float]] = {}
_CONTACT_RATE_LIMIT = 5
_CONTACT_RATE_WINDOW = 3600  # 1 hour

_CONTACT_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_CONTACT_VALID_SUBJECTS = {
    "Site Feedback or Suggestion",
    "Report a Problem",
    "Contribute or Collaborate",
    "Share Your ChattyHound Story",
    "Something Else",
}


def _contact_is_rate_limited(ip: str) -> bool:
    now = time.time()
    timestamps = _contact_rate_store.get(ip, [])
    timestamps = [t for t in timestamps if now - t < _CONTACT_RATE_WINDOW]
    _contact_rate_store[ip] = timestamps
    if len(timestamps) >= _CONTACT_RATE_LIMIT:
        return True
    timestamps.append(now)
    return False


@router.post("/api/contact")
async def contact_form(request: Request):
    try:
        # Get client IP
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else "unknown"

        # Rate limit
        if _contact_is_rate_limited(ip):
            return JSONResponse(status_code=429, content={
                "error": "You've sent too many messages recently. Please try again later."
            })

        body = await request.json()

        subject = (body.get("subject") or "").strip()
        email = (body.get("email") or "").strip()
        message = (body.get("message") or "").strip()

        # Validate
        if subject not in _CONTACT_VALID_SUBJECTS:
            return JSONResponse(status_code=400, content={"error": "Please select a valid subject."})
        if email:
            if len(email) > 254:
                return JSONResponse(status_code=400, content={"error": "Email address is too long."})
            if not _CONTACT_EMAIL_RE.match(email):
                return JSONResponse(status_code=400, content={"error": "Please enter a valid email address."})
        if not message:
            return JSONResponse(status_code=400, content={"error": "Please enter a message."})
        if len(message) > 5000:
            return JSONResponse(status_code=400, content={"error": "Message is too long (max 5,000 characters)."})

        # Send via Resend
        api_key = os.environ.get("RESEND_API_KEY", "")
        from_email = os.environ.get("CONTACT_FROM_EMAIL", "")
        to_email = os.environ.get("CONTACT_TO_EMAIL", "")

        if not api_key or not from_email or not to_email:
            logger.error("Contact form: missing email configuration env vars")
            return JSONResponse(status_code=500, content={
                "error": "Something went wrong sending your message. Please try again."
            })

        full_subject = f"ChattyHound Contact: {subject}"
        text_body = "\n".join([
            f"Subject: {subject}",
            f"From: {email or '(anonymous)'}",
            "",
            "Message:",
            "─" * 40,
            message,
            "─" * 40,
        ])

        payload = {
            "from": f"ChattyHound Contact <{from_email}>",
            "to": [to_email],
            "subject": full_subject,
            "text": text_body,
        }
        if email:
            payload["reply_to"] = email

        resp = _requests.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "ChattyHound/1.0",
            },
            timeout=15,
        )

        if resp.status_code >= 400:
            logger.error(f"Contact form: Resend API error {resp.status_code}: {resp.text}")
            return JSONResponse(status_code=500, content={
                "error": "Something went wrong sending your message. Please try again."
            })

        return JSONResponse(content={"ok": True, "message": "Message sent! Thank you. 🐾"})

    except Exception as e:
        logger.error(f"Contact form unexpected error: {e}")
        return JSONResponse(status_code=500, content={
            "error": "Something went wrong. Please try again."
        })
