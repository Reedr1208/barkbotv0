import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ── Threshold: if top-2 scores are within this many points, consider
#    swapping to the 2nd choice for distribution balance.
SCORE_PROXIMITY_THRESHOLD = 15


class ArchetypeScore(BaseModel):
    archetype_key: str = Field(description="The archetype key")
    score: int = Field(description="Fit score from 0-100 based on how well the evidence criteria matches this animal")
    reasoning: str = Field(description="One sentence explaining the score")


class ArchetypeRanking(BaseModel):
    rankings: List[ArchetypeScore] = Field(description="All archetypes scored and ranked from best to worst fit")


def build_persona_profile(openai_client: OpenAI, fact_profile: dict, archetypes: list, shelter_distribution: dict = None) -> dict:
    """
    Calls OpenAI to score all archetypes for this animal, then picks the best
    one — with a distribution-aware nudge when the top-2 are close.

    shelter_distribution: {archetype_key: count} for this dog's shelter only.
    """
    archetypes_context = []
    for arch in archetypes:
        archetypes_context.append({
            "archetype_key": arch["archetype_key"],
            "name": arch["name"],
            "evidence_criteria": arch["evidence_criteria"]
        })

    developer_prompt = (
        "You are an expert animal behavior analyst. "
        "Your task is to review an animal's factual profile and score EVERY archetype in the provided catalog "
        "on how well its evidence_criteria matches this specific animal. "
        "Score each archetype from 0 to 100 where 100 means the animal is a textbook match and 0 means no evidence at all. "
        "Be honest and precise — most animals will only strongly match 1-2 archetypes. "
        "Do NOT inflate scores to be polite. A score below 20 is fine for archetypes with no matching evidence."
    )

    user_prompt = (
        f"ANIMAL FACT PROFILE:\n{json.dumps(fact_profile, indent=2)}\n\n"
        f"AVAILABLE ARCHETYPES:\n{json.dumps(archetypes_context, indent=2)}\n\n"
        "Score every archetype for this animal. Return all of them ranked from best to worst fit."
    )

    logging.info(f"Selecting archetype for {fact_profile.get('animal_id')}...")

    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=ArchetypeRanking
    )

    parsed = response.choices[0].message.parsed
    rankings = sorted(parsed.rankings, key=lambda x: x.score, reverse=True)

    # ── Pick the best archetype, with distribution nudge ──────────────
    best = rankings[0]
    chosen_key = best.archetype_key
    chosen_reasoning = best.reasoning
    was_nudged = False

    if len(rankings) >= 2 and shelter_distribution:
        runner_up = rankings[1]
        gap = best.score - runner_up.score

        if gap <= SCORE_PROXIMITY_THRESHOLD:
            # Top-2 are close — check if runner-up is under-represented
            total = sum(shelter_distribution.values()) or 1
            num_archetypes = len(archetypes) or 1
            ideal_share = total / num_archetypes

            best_count = shelter_distribution.get(best.archetype_key, 0)
            runner_count = shelter_distribution.get(runner_up.archetype_key, 0)

            # Nudge if runner-up is below ideal AND best is at/above ideal
            if runner_count < ideal_share and best_count >= ideal_share:
                chosen_key = runner_up.archetype_key
                chosen_reasoning = (
                    f"[Distribution nudge: top-2 within {gap}pts "
                    f"({best.archetype_key}={best.score}, {runner_up.archetype_key}={runner_up.score}); "
                    f"shelter counts: {best.archetype_key}={best_count}, "
                    f"{runner_up.archetype_key}={runner_count}, ideal≈{ideal_share:.0f}] "
                    f"{runner_up.reasoning}"
                )
                was_nudged = True
                logging.info(
                    f"  Distribution nudge for {fact_profile.get('animal_id')}: "
                    f"{best.archetype_key}({best.score}) → {runner_up.archetype_key}({runner_up.score}) "
                    f"(gap={gap}, shelter: {best.archetype_key}={best_count}, {runner_up.archetype_key}={runner_count})"
                )

    # Find chosen archetype to include characters, linguistic_style, etc.
    chosen_arch = next((a for a in archetypes if a["archetype_key"] == chosen_key), None)

    return {
        "animal_id": fact_profile.get("animal_id"),
        "primary_archetype_key": chosen_key,
        "selection_reasoning": chosen_reasoning,
        "characters": chosen_arch["characters"] if chosen_arch else "",
        "linguistic_style": chosen_arch["linguistic_style"] if chosen_arch else "",
        "creative_quirks": chosen_arch.get("creative_quirks", []) if chosen_arch else [],
        "personality": chosen_arch.get("personality", []) if chosen_arch else [],
        "schema_version": "persona_v3",
        "scoring_model": "gpt-4o-mini",
        "scoring_params_jsonb": {"temperature": 0.2},
        "_archetype_scores": {r.archetype_key: r.score for r in rankings},
        "_was_nudged": was_nudged,
    }
