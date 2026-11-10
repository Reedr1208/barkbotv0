"""
Shared AI-enrichment helpers (fact extraction → persona → system prompt).

Used by both the scheduled `generate_prompts` job and the admin backfill so the
per-dog pipeline and the "limited profile" rules live in exactly one place.

Every active dog is enriched and chattable. Dogs whose shelter bio is shorter
than their shelter's minimum length are "limited profile" dogs:
  • they skip LLM archetype scoring and get the generic persona
    (GENERIC_ARCHETYPE_KEY) instead of one of the evidence-based archetypes,
  • their system prompt includes a note telling the dog not to invent details,
  • the next-dog ranker serves them only after all richer matches,
  • the UI shows a "Limited info" badge on their chat banner.

Keep imports here lightweight — routes/dog_ranking.py imports the constants.
"""

import logging
import os
import sys

logger = logging.getLogger("barkbot.enrichment")

# persona_archetypes row for limited-profile dogs. Stored with active = false so
# it is never offered to the LLM archetype scorer (which loads active rows only).
GENERIC_ARCHETYPE_KEY = "generic_pup"

# Minimum shelter-bio length (characters) for a dog to receive a full,
# evidence-based archetype. Below this the dog gets the generic persona.
# Keys must match the live shelter_id values.
_BIO_MIN_LENGTH = {
    "NYCACC": 1500,
    "MP": 1000,     # Muddy Paws
    "PACC": 800,    # Pima Animal Care Center
    "BDW": 800,     # Bideawee (~280 chars of structured header + ≥~500 chars narrative)
    "SFSPCA": 600,  # SF SPCA (~150 chars header + ≥~450 narrative; templated litter bios fall below)
    "MCACC": 6000,
    "PAWSCH": 1200,
    "WWLA": 1000, "HHS": 1000, "PHP": 1000, "SAPA": 1000, "PAWSCO": 1000,
    "HSSA": 500,
    "RCHS": 500, "DPA": 500, "NHS": 500, "EHR": 500, "MV": 500, "RDR": 500,
}
_DEFAULT_BIO_MIN_LENGTH = 401  # original default rule: bio must be > 400 chars


def bio_min_length(shelter_id) -> int:
    return _BIO_MIN_LENGTH.get((shelter_id or "").upper(), _DEFAULT_BIO_MIN_LENGTH)


def is_limited_profile(shelter_id, bio_length) -> bool:
    """True when the bio is too short for an evidence-based archetype."""
    return int(bio_length or 0) < bio_min_length(shelter_id)


def is_generic_archetype(archetype_key) -> bool:
    return archetype_key == GENERIC_ARCHETYPE_KEY


# ── Catalog / distribution loaders ───────────────────────────────────

def load_archetypes(sb):
    """Return (scoring_archetypes, generic_archetype_or_None)."""
    rows = sb.table("persona_archetypes").select("*").execute().data or []
    scoring = [r for r in rows if r.get("active") and r.get("archetype_key") != GENERIC_ARCHETYPE_KEY]
    generic = next((r for r in rows if r.get("archetype_key") == GENERIC_ARCHETYPE_KEY), None)
    if generic is None:
        logger.error("persona_archetypes row %r is missing — limited-profile dogs cannot be enriched. "
                     "Run scripts/migrate_generic_archetype.py.", GENERIC_ARCHETYPE_KEY)
    return scoring, generic


def _fetch_all(query_builder, page_size=1000):
    rows, offset = [], 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        rows.extend(res.data)
        if len(res.data) < page_size:
            return rows
        offset += page_size


def load_shelter_distributions(sb, persona_rows=None):
    """{shelter_id: {archetype_key: count}} for archetype balancing.

    Generic (limited-profile) dogs are excluded so they don't skew the balance
    of the evidence-based archetypes.
    """
    if persona_rows is None:
        persona_rows = _fetch_all(sb.table("animal_persona_profiles").select("animal_id, primary_archetype_key"))
    persona_rows = [r for r in persona_rows
                    if r.get("animal_id") and r.get("primary_archetype_key")
                    and not is_generic_archetype(r.get("primary_archetype_key"))]

    shelter_lookup = {}
    aids = [r["animal_id"] for r in persona_rows]
    for i in range(0, len(aids), 500):
        res = sb.table("animals").select("animal_id, shelter_id").in_("animal_id", aids[i:i + 500]).execute()
        for r in res.data:
            shelter_lookup[r["animal_id"]] = r.get("shelter_id") or "unknown"

    dist = {}
    for r in persona_rows:
        sid = shelter_lookup.get(r["animal_id"], "unknown")
        key = r["primary_archetype_key"]
        dist.setdefault(sid, {})
        dist[sid][key] = dist[sid].get(key, 0) + 1
    return dist


# ── Persona helpers ──────────────────────────────────────────────────

def _limited_info_note(shelter_name) -> str:
    shelter = shelter_name or "the shelter"
    return (
        "PROFILE COMPLETENESS: LIMITED INFO\n"
        "Your shelter profile has very little information about you, so your voice above is a general "
        "happy-pup personality rather than something drawn from your bio.\n"
        "- Never invent specific personality traits, history, habits, likes or dislikes, or behavior details "
        "that are not in your profile.\n"
        f"- When asked about something your profile does not cover, cheerfully admit you do not know yet and "
        f"encourage the human to reach out to {shelter} for more details (share your adoption link when helpful).\n"
        "- Lean on what IS known (name, age, size, breed, sex, location) and keep the fun in your voice, "
        "not in made-up facts."
    )


def generic_persona_profile(animal_id, generic_archetype, shelter_name, bio_length, min_length) -> dict:
    """Persona profile for a limited-profile dog (no LLM call)."""
    return {
        "animal_id": animal_id,
        "primary_archetype_key": GENERIC_ARCHETYPE_KEY,
        "selection_reasoning": (
            f"Limited profile: shelter bio is {bio_length} chars, below this shelter's "
            f"{min_length}-char minimum for archetype scoring. Assigned the generic persona."
        ),
        "characters": generic_archetype.get("characters") or "",
        "linguistic_style": generic_archetype.get("linguistic_style") or "",
        "creative_quirks": generic_archetype.get("creative_quirks") or [],
        "personality": generic_archetype.get("personality") or [],
        "profile_completeness_note": _limited_info_note(shelter_name),
        "schema_version": "persona_v3",
    }


# ── Per-dog pipeline ─────────────────────────────────────────────────

def _ensure_pipeline_importable():
    api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)


def enrich_dog(sb, openai_client, animal_record, scoring_archetypes, generic_archetype,
               shelter_distributions, shelter_id_fallback=None) -> dict:
    """Run fact extraction → persona → prompt render for one dog and upsert
    animal_fact_profiles, animal_persona_profiles and system_prompts_v2.

    animal_record: full `animals` row (will be copied, not mutated).
    shelter_distributions: mutated in place when an evidence-based archetype is assigned.
    Returns {animal_id, dog_name, archetype, limited}. Raises on failure.
    """
    _ensure_pipeline_importable()
    from pipeline.extract_fact_profiles import extract_fact_profile
    from pipeline.build_persona_profiles import build_persona_profile
    from pipeline.render_system_prompts_v2 import render_system_prompt, validate_system_prompt

    record = dict(animal_record)
    aid = record["animal_id"]
    record_hash = record.get("record_hash", "none")
    updated_at = record.get("updated_at")
    adoption_url = record.get("shelter_profile_url")
    shelter_name = record.get("shelter_name")
    shelter_id = record.get("shelter_id") or shelter_id_fallback or "unknown"
    bio = record.get("bio") or ""

    for key in ("id", "record_hash", "created_at", "updated_at", "last_scrape_run_id"):
        record.pop(key, None)

    limited = is_limited_profile(shelter_id, len(bio))
    if limited and not generic_archetype:
        raise RuntimeError(f"generic archetype {GENERIC_ARCHETYPE_KEY!r} not found in persona_archetypes")

    # 1. Fact extraction (all dogs — even sparse records yield name/age/size/breed facts)
    fact_profile = extract_fact_profile(openai_client, record).model_dump()
    fact_profile.update({
        "animal_id": aid,
        "source_record_hash": record_hash,
        "schema_version": "fact_v1",
        "extraction_model": "gpt-5.4-mini",
        "extraction_params_jsonb": {"temperature": 0.2},
        "info_refreshed_at": updated_at,
        "adoption_url": adoption_url,
        "shelter_name": shelter_name,
    })
    sb.table("animal_fact_profiles").upsert(fact_profile).execute()
    fact_profile["full_bio"] = bio

    # 2. Persona
    if limited:
        persona_profile = generic_persona_profile(aid, generic_archetype, shelter_name,
                                                  len(bio), bio_min_length(shelter_id))
    else:
        persona_profile = build_persona_profile(openai_client, fact_profile, scoring_archetypes,
                                                shelter_distributions.get(shelter_id, {}))
        assigned = persona_profile.get("primary_archetype_key")
        if assigned:
            shelter_distributions.setdefault(shelter_id, {})
            shelter_distributions[shelter_id][assigned] = shelter_distributions[shelter_id].get(assigned, 0) + 1

    sb.table("animal_persona_profiles").upsert({
        "animal_id": aid,
        "source_record_hash": record_hash,
        "primary_archetype_key": persona_profile.get("primary_archetype_key"),
        "selection_reasoning": persona_profile.get("selection_reasoning"),
    }).execute()

    # 3. Prompt render (deterministic)
    system_prompt = render_system_prompt(fact_profile, persona_profile)
    validation = validate_system_prompt(system_prompt)
    sb.table("system_prompts_v2").upsert({
        "animal_id": aid,
        "prompt_version": "v3",
        "source_record_hash": record_hash,
        "system_prompt": system_prompt,
        "render_context_jsonb": {
            "fact_profile_used": True,
            "persona_profile_used": True,
            "archetype": persona_profile.get("primary_archetype_key"),
            "limited_profile": limited,
        },
        "validation_results_jsonb": validation,
        "is_active": True,
    }).execute()

    return {
        "animal_id": aid,
        "dog_name": fact_profile.get("dog_name", ""),
        "archetype": persona_profile.get("primary_archetype_key"),
        "limited": limited,
    }
