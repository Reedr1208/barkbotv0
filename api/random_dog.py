import json
import os
import random
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta
from supabase import create_client

def get_supabase_client():
    supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("storage_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase environment variables.")
    return create_client(supabase_url, supabase_key)

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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            viewed_str = query_params.get("viewed", [""])[0]
            viewed_list = [aid.strip() for aid in viewed_str.split(",") if aid.strip()]
            viewed_ids = set(viewed_list)
            email = query_params.get("email", [""])[0].strip().lower()
            # animal_id override: fetch a specific dog directly (for Saved/chat resume)
            animal_id_override = query_params.get("animal_id", [""])[0].strip() or None

            client = get_supabase_client()
            
            # ── Direct lookup by animal_id (for Saved Dogs / Resume Chat) ──
            if animal_id_override:
                active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight").eq("animal_id", animal_id_override).limit(1).execute()
                prompts_res = client.table("system_prompts_v2").select("animal_id").eq("animal_id", animal_id_override).limit(1).execute()
                profile_res = client.table("animals").select("*").eq("animal_id", animal_id_override).limit(1).execute()
                fact_res = client.table("animal_fact_profiles").select("intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, strengths_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb").eq("animal_id", animal_id_override).limit(1).execute()
                
                if not active_res.data or not profile_res.data:
                    self._send_response(404, {"error": "Dog not found."})
                    return
                active_dog = active_res.data[0]
                profile = profile_res.data[0]
                profile["name"] = active_dog.get("name") or "Unknown"
                profile["gender"] = active_dog.get("gender") or "Unknown"
                
                facts_data = fact_res.data[0] if fact_res.data else {}
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
                
                profile["preferences_matched"] = False
                profile["user_has_preferences"] = False
                profile["match_details"] = {}
                internal_keys = ["id", "record_hash", "created_at", "last_scrape_run_id"]
                for key in internal_keys:
                    profile.pop(key, None)
                supabase_url_val = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
                bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
                profile["image_base_url"] = f"{supabase_url_val}/storage/v1/object/public/{bucket}/"
                self._send_response(200, profile)
                return

            # Parse user coordinates from query params for proximity matching
            user_lat = None
            user_lon = None
            try:
                lat_str = query_params.get("lat", [""])[0].strip()
                lon_str = query_params.get("lon", [""])[0].strip()
                if lat_str and lon_str:
                    user_lat = float(lat_str)
                    user_lon = float(lon_str)
            except Exception:
                pass

            closer_region = None
            if user_lat is not None and user_lon is not None:
                # Tucson, AZ coordinates: 32.2226, -110.9747
                # New York, NY coordinates: 40.7128, -74.0060
                dist_tucson = (user_lat - 32.2226)**2 + (user_lon - (-110.9747))**2
                dist_ny = (user_lat - 40.7128)**2 + (user_lon - (-74.0060))**2
                closer_region = "TUCSON" if dist_tucson < dist_ny else "NYC"

            # Fetch all dog IDs, names, and filterable fields from active_dogs
            active_res = client.table("active_dogs").select("animal_id, name, gender, age, weight, shelter_id").execute()
            if not active_res.data:
                self._send_response(404, {"error": "No dogs found in active_dogs."})
                return
                
            active_dogs = {row["animal_id"]: row for row in active_res.data}
            
            # Fetch from animal_persona_profiles to get archetype data and freshness
            persona_res = client.table("animal_persona_profiles").select("animal_id, primary_archetype_key, updated_at").execute()
            persona_data = {row["animal_id"]: row for row in persona_res.data}
            
            # Intersect to find valid current dogs that have a persona
            valid_ids = list(set(active_dogs.keys()).intersection(persona_data.keys()))
            

            if not valid_ids:
                self._send_response(404, {"error": "No dogs with generated personas found."})
                return
                
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
            if email:
                pref_res = client.table("user_preferences").select("*").eq("email", email).limit(1).execute()
                if pref_res.data:
                    preferences = pref_res.data[0]
            
            if not preferences:
                # Fallback to query params for guest users
                q_gender = query_params.get("gender", [""])[0].strip().lower()
                q_age = query_params.get("age_group", [""])[0].strip().lower()
                q_size = query_params.get("size", [""])[0].strip().lower()
                q_location = query_params.get("location", [""])[0].strip().lower()
                if q_gender or q_age or q_size or q_location:
                    preferences = {
                        "gender": q_gender or "any",
                        "age_group": q_age or "any",
                        "size": q_size or "any",
                        "location": q_location or "any"
                    }

            # Apply preferences filtering if preferences are configured
            preferences_matched = False
            best_match_details = {}
            scored_dogs = {aid: 0 for aid in valid_ids}
            preferences_configured = False
            
            if preferences:
                pref_gender = preferences.get("gender", "any")
                pref_age = preferences.get("age_group", "any")
                pref_size = preferences.get("size", "any")
                pref_location = preferences.get("location", "any")
                
                # Triggers for active categories
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
                            "location": {"active": has_location, "preferred": pref_location, "actual": "Tucson, AZ" if dog.get("shelter_id") in ("PIMA", "HSSA") else "New York, NY", "matched": False}
                        }
                        
                        # 1. Gender Filter
                        if has_gender:
                            if matches_gender(dog.get("gender"), pref_gender):
                                score += 1
                                details["gender"]["matched"] = True
                                
                        # 2. Age Filter
                        if has_age:
                            dog_age_group = classify_age_group(dog.get("age"))
                            if dog_age_group == pref_age:
                                score += 1
                                details["age"]["matched"] = True
                            details["age"]["actual"] = f"{dog.get('age') or 'Unknown'} ({dog_age_group.capitalize()})"
                                
                        # 3. Size Filter
                        if has_size:
                            dog_weight = parse_weight_lbs(dog.get("weight"))
                            dog_size_class = "Unknown"
                            if dog_weight > 0:
                                if dog_weight < 25:
                                    dog_size_class = "small"
                                elif dog_weight < 60:
                                    dog_size_class = "medium"
                                else:
                                    dog_size_class = "large"
                                    
                            if dog_size_class == pref_size:
                                score += 1
                                details["size"]["matched"] = True
                            details["size"]["actual"] = f"{dog.get('weight') or 'Unknown'} ({dog_size_class.capitalize()})"
                            
                        # 4. Location Filter
                        if has_location:
                            if pref_location == "tucson":
                                if dog.get("shelter_id") in ("PIMA", "HSSA"):
                                    score += 1
                                    details["location"]["matched"] = True
                            else:
                                if dog.get("shelter_id") in ("MUDDYPAWS", "NYCACC"):
                                    score += 1
                                    details["location"]["matched"] = True
                        else:
                            # User has no location preference but coordinates are available
                            if closer_region == "NYC" and dog.get("shelter_id") in ("MUDDYPAWS", "NYCACC"):
                                score += 0.8
                            elif closer_region == "TUCSON" and dog.get("shelter_id") in ("PIMA", "HSSA"):
                                score += 0.8

                        # Tie-breaker for archetype diversity (layer below preferences)
                        dog_arch = persona_data[aid].get("primary_archetype_key")
                        if dog_arch and dog_arch not in last_2_archetypes:
                            score += 0.5
                            
                        scored_dogs[aid] = score
                        best_match_details[aid] = details
            else:
                # If no preferences configured, score based on closer shelter (if available) and archetype diversity
                for aid in valid_ids:
                    score = 0
                    dog = active_dogs[aid]
                    if closer_region == "NYC" and dog.get("shelter_id") in ("MUDDYPAWS", "NYCACC"):
                        score += 0.8
                    elif closer_region == "TUCSON" and dog.get("shelter_id") in ("PIMA", "HSSA"):
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
                    fresh_status[aid] = True # default to fresh

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
                        # Add a baseline weight so even empty bios have a non-zero chance,
                        # but longer bios are significantly more likely to be chosen.
                        weights.append(lengths.get(cid, 0) + 10)
                        
                    return random.choices(candidates, weights=weights, k=1)[0]
                except Exception as e:
                    # Fallback to uniform random if DB fetch fails
                    return random.choice(candidates)
            
            random_id = None

            if unviewed_ids:
                # Find maximum score among remaining unviewed dogs
                max_unviewed_score = max(scored_dogs[aid] for aid in unviewed_ids)
                best_unviewed_candidates = [aid for aid in unviewed_ids if scored_dogs[aid] == max_unviewed_score]
                
                # Prioritize fresh among these top unviewed candidates
                unviewed_fresh = [aid for aid in best_unviewed_candidates if fresh_status[aid]]
                unviewed_stale = [aid for aid in best_unviewed_candidates if not fresh_status[aid]]
                
                if unviewed_fresh:
                    random_id = select_weighted_dog(unviewed_fresh)
                else:
                    random_id = select_weighted_dog(unviewed_stale)
            else:
                # All dogs viewed. Reset viewed list and select from all top-scoring dogs in the system
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
                # A match is strong if it matched at least one preference (score >= 1.0)
                # and either it's the max overall score or it meets a minimum threshold.
                max_overall_score = max(scored_dogs.values()) if scored_dogs else 0
                preferences_matched = (scored_dogs[random_id] >= 1.0 and (scored_dogs[random_id] == max_overall_score or scored_dogs[random_id] >= 1.0))
            
            # Fetch the full profile
            profile_res = client.table("animals").select("*").eq("animal_id", random_id).limit(1).execute()
            if not profile_res.data:
                self._send_response(404, {"error": "Profile not found in animals table."})
                return
                
            profile = profile_res.data[0]
            
            # Add the name, gender and facts
            profile["name"] = active_dogs[random_id].get("name") or "Unknown"
            profile["gender"] = active_dogs[random_id].get("gender") or "Unknown"
            
            fact_res = client.table("animal_fact_profiles").select("intro_summary, important_facts_jsonb, backstory_summary, risk_flags_jsonb, strengths_jsonb, challenges_jsonb, ideal_home_jsonb, other_animals_notes, people_notes, containment_notes, medical_notes, adoption_process_notes, unknowns_jsonb").eq("animal_id", random_id).limit(1).execute()
            facts_data = fact_res.data[0] if fact_res.data else {}
            
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
            profile["preferences_matched"] = preferences_matched
            profile["user_has_preferences"] = (preferences is not None)
            profile["match_details"] = best_match_details.get(random_id, {})
            
            # Clean up internal fields before sending to frontend
            internal_keys = ["id", "record_hash", "created_at", "last_scrape_run_id"]
            for key in internal_keys:
                profile.pop(key, None)
                
            supabase_url = os.environ.get("storage_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
            bucket = os.environ.get("SUPABASE_BUCKET", "animal-images")
            profile["image_base_url"] = f"{supabase_url}/storage/v1/object/public/{bucket}/"
                
            self._send_response(200, profile)
            
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))
