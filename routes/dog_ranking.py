"""
Dog ranking engine — single source of truth for next-dog selection.

This module contains all filtering, scoring, and selection logic for the
"Next Dog" feature.  Edit the weights at the top of this file to fine-tune
the ranking formula.

Terminology
-----------
  hard filter : pass/fail gate — if a dog fails, it's excluded entirely
  soft score  : additive bonus — dogs with higher scores are preferred
  tier        : freshness partition — fresh dogs are preferred over stale
"""

import logging
import random
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("barkbot.ranking")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TUNABLE WEIGHTS — edit these to change ranking behavior
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WEIGHT_ARCHETYPE_VARIETY = 0.5   # Bonus for archetype not in last 2 shown
FRESHNESS_WINDOW_DAYS    = 3     # Profiles updated within N days are "fresh"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HARD FILTERS  (pass/fail — not scored)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _clean_loc(s):
    """Normalise location string for comparison."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()


def _matches_gender(dog_gender, pref_gender):
    if not pref_gender or pref_gender == "any":
        return True
    if not dog_gender:
        return False
    dog_gender = dog_gender.lower().strip()
    pref_gender = pref_gender.lower().strip()
    if pref_gender == "male":
        return "female" not in dog_gender and "male" in dog_gender
    return pref_gender in dog_gender


def apply_hard_filters(valid_ids, active_dogs, shelters_map, preferences):
    """
    Apply all preference-based hard filters.

    Returns the filtered list of animal_ids.  If zero dogs survive
    all filters the caller should return a no-matches response.

    Filters applied (in order):
      1. Location
      2. Gender
      3. Age bucket   (unknowns pass through)
      4. Weight class  (unknowns pass through)
      5. Altered status (unknowns pass through)
      6. Energy level  (strict — confirmed only)
      7. Good with dogs (strict — confirmed "yes" only)
      8. House trained  (strict — confirmed "yes" only)
    """
    pref_location = (preferences.get("location") or "any").strip()
    pref_gender   = (preferences.get("gender") or "any").strip().lower()
    pref_age      = (preferences.get("age_group") or "any").strip().lower()
    pref_size     = (preferences.get("size") or "any").strip().lower()
    pref_altered  = (preferences.get("altered") or "any").strip().lower()
    pref_energy   = (preferences.get("energy") or "any").strip().lower()
    pref_dogs     = preferences.get("dogs", False)
    pref_house    = preferences.get("house_trained", False)

    ids = list(valid_ids)

    # 1. Location
    if pref_location not in ("any", "all"):
        ids = [aid for aid in ids
               if _clean_loc(pref_location) ==
                  _clean_loc(shelters_map.get(active_dogs[aid].get("shelter_id"), {}).get("location_display_name", ""))]

    # 2. Gender
    if pref_gender != "any":
        ids = [aid for aid in ids if _matches_gender(active_dogs[aid].get("gender"), pref_gender)]

    # 3. Age (unknowns pass through)
    if pref_age != "any":
        ids = [aid for aid in ids
               if (active_dogs[aid].get("age_bucket") or "N/A") == "N/A"
               or pref_age in (active_dogs[aid].get("age_bucket") or "").lower()]

    # 4. Size (unknowns pass through)
    if pref_size != "any":
        ids = [aid for aid in ids
               if (active_dogs[aid].get("weight_class") or "N/A") == "N/A"
               or pref_size in (active_dogs[aid].get("weight_class") or "").lower()]

    # 5. Altered status (unknowns pass through)
    if pref_altered != "any":
        filtered = []
        for aid in ids:
            status = (active_dogs[aid].get("altered_status") or "N/A").lower()
            if status == "n/a":
                filtered.append(aid)
            elif pref_altered == "altered" and status in ("spayed", "neutered"):
                filtered.append(aid)
            elif pref_altered == "unaltered" and status == "unaltered":
                filtered.append(aid)
        ids = filtered

    # 6. Energy level (strict)
    if pref_energy != "any":
        ids = [aid for aid in ids
               if pref_energy == (active_dogs[aid].get("energy_level") or "").lower()]

    # 7. Good with dogs (strict — only confirmed "yes")
    if pref_dogs:
        ids = [aid for aid in ids
               if (active_dogs[aid].get("good_with_dogs") or "").lower() == "yes"]

    # 8. House trained (strict — only confirmed "yes")
    if pref_house:
        ids = [aid for aid in ids
               if (active_dogs[aid].get("house_trained") or "").lower() == "yes"]

    return ids


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SOFT SCORING  (additive bonuses for ranking within filtered pool)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def score_candidates(candidates, persona_data, viewed_list):
    """
    Score each candidate dog.  Higher score = more desirable to show next.

    Current factors
    ───────────────
    • Archetype variety  (+0.5 if archetype not in last 2 shown)

    Returns {animal_id: score} dict.
    """
    # Determine last 2 unique archetypes from viewed history
    last_2_archetypes = set()
    for aid in reversed(viewed_list):
        if aid in persona_data:
            arch = persona_data[aid].get("primary_archetype_key")
            if arch:
                last_2_archetypes.add(arch)
        if len(last_2_archetypes) >= 2:
            break

    scores = {}
    for aid in candidates:
        score = 0.0
        dog_arch = persona_data.get(aid, {}).get("primary_archetype_key")
        if dog_arch and dog_arch not in last_2_archetypes:
            score += WEIGHT_ARCHETYPE_VARIETY
        scores[aid] = score

    return scores


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SELECTION  (pick one dog from scored candidates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _freshness_map(candidates, persona_data):
    """Classify each candidate as fresh (True) or stale (False)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_WINDOW_DAYS)
    status = {}
    for aid in candidates:
        dt_str = persona_data.get(aid, {}).get("updated_at", "")
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        try:
            updated_at = datetime.fromisoformat(dt_str)
            status[aid] = (updated_at >= cutoff)
        except Exception:
            status[aid] = True  # treat parse failures as fresh
    return status


def _pick_bio_weighted(candidates, client):
    """
    Weighted random selection favouring dogs with richer bios.

    Weight = min(bio_length, 800) / 10 + 10
    This gives dogs with longer bios higher probability without
    completely excluding dogs with short bios.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    try:
        res = client.table("animals").select("animal_id, bio").in_("animal_id", candidates).execute()
        lengths = {row["animal_id"]: len(row.get("bio") or "") for row in res.data}
        weights = [min(lengths.get(cid, 0), 800) / 10.0 + 10 for cid in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
    except Exception:
        return random.choice(candidates)


def select_dog(candidates, scores, persona_data, viewed_ids, client):
    """
    Select a single dog to show next.

    Priority order
    ──────────────
    1. Unviewed dogs first (ensures no repeats until full loop)
    2. Highest score within the unviewed/viewed pool
    3. Fresh profiles over stale (within same score tier)
    4. Bio-weighted random within same tier

    When all candidates have been viewed, selects from the full pool
    — this enables endless looping.
    """
    viewed_set = set(viewed_ids) if not isinstance(viewed_ids, set) else viewed_ids
    unviewed = [aid for aid in candidates if aid not in viewed_set]

    # Pick from unviewed if any remain; otherwise loop over all
    pool = unviewed if unviewed else candidates

    if not pool:
        return None

    freshness = _freshness_map(pool, persona_data)
    max_score = max(scores.get(aid, 0) for aid in pool)
    best = [aid for aid in pool if scores.get(aid, 0) == max_score]

    # Prefer fresh within best-scored tier
    fresh = [aid for aid in best if freshness.get(aid, True)]
    stale = [aid for aid in best if not freshness.get(aid, True)]

    if fresh:
        return _pick_bio_weighted(fresh, client)
    return _pick_bio_weighted(stale, client)
