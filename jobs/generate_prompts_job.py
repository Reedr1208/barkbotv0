"""
Generate prompts job — extracted from api/generate_prompts.py for serverful execution.

Runs the full pipeline (fact extraction → persona → prompt rendering) for every
active dog that needs a new or refreshed prompt. Called directly by
APScheduler — no HTTP handler, no subprocess.

All active dogs are enriched (and therefore chattable). Dogs whose bio is below
their shelter's minimum length get the generic "limited profile" persona
instead of an LLM-scored archetype — see jobs/lib/enrichment.py.
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

from openai import OpenAI

from jobs.lib.db import get_supabase_client
from jobs.lib.enrichment import (
    enrich_dog,
    is_generic_archetype,
    is_limited_profile,
    load_archetypes,
    load_shelter_distributions,
)

logger = logging.getLogger("barkbot.jobs.generate_prompts")

# Allow up to 15 minutes per run.
MAX_EXECUTION_TIME = 900
PROMPT_REFRESH_DAYS = 3

# Target priorities (lower runs first)
PRIORITY_RICH_NEW = 0      # rich-bio dog with no prompt, or upgrading from generic
PRIORITY_LIMITED_NEW = 1   # limited dog with no prompt, or downgrading to generic
PRIORITY_STALE = 2         # routine refresh of prompts older than PROMPT_REFRESH_DAYS


def _fetch_all(query_builder, page_size=1000):
    rows, offset = [], 0
    while True:
        res = query_builder.range(offset, offset + page_size - 1).execute()
        rows.extend(res.data)
        if len(res.data) < page_size:
            return rows
        offset += page_size


def _parse_ts(dt_str):
    if not dt_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def run():
    """Execute the generate_prompts pipeline. Called by APScheduler."""
    start_time = time.time()
    logger.info("Starting generate_prompts job...")

    try:
        sb_client = get_supabase_client()
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        scoring_archetypes, generic_archetype = load_archetypes(sb_client)

        # 1. Active dogs
        active_rows = _fetch_all(sb_client.table("active_dogs").select("animal_id, shelter_id"))
        active_dogs_map = {r["animal_id"]: r.get("shelter_id") for r in active_rows}
        if not active_dogs_map:
            logger.info("No active dogs found in active_dogs.")
            return {"ok": True, "processed": 0, "message": "No active dogs found"}

        # 2. Bio lengths (only dogs with a scraped `animals` row can be enriched)
        active_ids = list(active_dogs_map.keys())
        bio_lengths = {}
        for i in range(0, len(active_ids), 100):
            res = sb_client.table("animals").select("animal_id, bio_length") \
                .in_("animal_id", active_ids[i:i + 100]).execute()
            for r in res.data:
                bio_lengths[r["animal_id"]] = r.get("bio_length") or 0

        # 3. Existing prompts + personas
        prompt_updated = {r["animal_id"]: r.get("updated_at")
                          for r in _fetch_all(sb_client.table("system_prompts_v2").select("animal_id, updated_at"))}
        persona_rows = _fetch_all(sb_client.table("animal_persona_profiles").select("animal_id, primary_archetype_key"))
        persona_keys = {r["animal_id"]: r.get("primary_archetype_key") for r in persona_rows}

        # 4. Build prioritized target list
        stale_before = datetime.now(timezone.utc) - timedelta(days=PROMPT_REFRESH_DAYS)
        targets = []
        limited_total = 0
        for aid, bio_len in bio_lengths.items():
            limited = is_limited_profile(active_dogs_map.get(aid), bio_len)
            limited_total += limited
            has_prompt = aid in prompt_updated and aid in persona_keys
            tier_mismatch = has_prompt and (is_generic_archetype(persona_keys[aid]) != limited)
            updated_at = _parse_ts(prompt_updated.get(aid))

            if not has_prompt or tier_mismatch:
                priority = PRIORITY_LIMITED_NEW if limited else PRIORITY_RICH_NEW
            elif updated_at < stale_before:
                priority = PRIORITY_STALE
            else:
                continue
            targets.append((priority, updated_at, aid))

        targets.sort()
        target_ids = [t[2] for t in targets]
        by_priority = {p: sum(1 for t in targets if t[0] == p) for p in (0, 1, 2)}
        logger.info(
            f"Found {len(target_ids)} dogs requiring prompt generation "
            f"(rich-new/upgrade={by_priority[0]}, limited-new/downgrade={by_priority[1]}, stale={by_priority[2]}); "
            f"{limited_total}/{len(bio_lengths)} profiled active dogs are limited-profile."
        )

        if not target_ids:
            return {"ok": True, "processed": 0, "message": "Nothing to refresh"}

        # 5. Per-shelter archetype distribution (excludes generic dogs)
        shelter_distributions = load_shelter_distributions(sb_client, persona_rows)

        processed_count = 0
        limited_count = 0
        for aid in target_ids:
            if time.time() - start_time > MAX_EXECUTION_TIME:
                logger.info("Nearing execution time limit. Halting gracefully.")
                break

            logger.info(f"Processing animal_id: {aid}")
            animal_res = sb_client.table("animals").select("*").eq("animal_id", aid).limit(1).execute()
            if not animal_res.data:
                continue

            try:
                result = enrich_dog(
                    sb_client, openai_client, animal_res.data[0],
                    scoring_archetypes, generic_archetype, shelter_distributions,
                    shelter_id_fallback=active_dogs_map.get(aid),
                )
                processed_count += 1
                limited_count += result["limited"]
            except Exception as gen_exc:
                logger.error(f"Failed to generate/upsert for {aid}: {gen_exc}")

        elapsed = time.time() - start_time
        logger.info(f"Job completed. Processed {processed_count} prompts ({limited_count} limited-profile) in {elapsed:.2f}s.")
        return {"ok": True, "processed": processed_count, "limited": limited_count, "elapsed_seconds": elapsed}

    except Exception as e:
        logger.exception("An unexpected error occurred in generate_prompts.")
        return {"ok": False, "error": str(e)}
