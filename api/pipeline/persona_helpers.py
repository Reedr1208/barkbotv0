"""
Centralized persona helpers — shared by scheduled job, admin route, and backfill.

Ensures all three entry points produce identical DB row shapes and use the same
model constants. Avoids metadata drift between entry points.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("barkbot.pipeline.persona_helpers")


def persona_profile_to_db_row(persona_profile: dict, source_record_hash: str, fingerprint_dict: Optional[dict] = None) -> dict:
    """
    Canonical serializer for the animal_persona_profiles table.
    All three entry points (job, admin, backfill) must use this.
    """
    row = {
        "animal_id": persona_profile.get("animal_id"),
        "source_record_hash": source_record_hash,
        "primary_archetype_key": persona_profile.get("primary_archetype_key"),
        "selection_reasoning": persona_profile.get("selection_reasoning"),
    }

    if fingerprint_dict and len(fingerprint_dict) > 0:
        # Ensure schema_version is set correctly (LLM may have overwritten/omitted it)
        fingerprint_dict["schema_version"] = "persona_v4"
        row["persona_fingerprint_jsonb"] = fingerprint_dict
        row["schema_version"] = "persona_v4"
        row["enrichment_model"] = persona_profile.get("enrichment_model")
        row["enrichment_params_jsonb"] = persona_profile.get("enrichment_params_jsonb")
    else:
        row["schema_version"] = "persona_v3"

    return row


def build_render_context(fact_profile: dict, persona_profile: dict, fingerprint_dict: Optional[dict] = None) -> dict:
    """
    Build the render_context_jsonb stored alongside the system prompt.
    Includes a compact behavior deck when v4 fingerprint is available.
    """
    ctx = {
        "fact_profile_used": True,
        "persona_profile_used": True,
        "archetype": persona_profile.get("primary_archetype_key"),
    }

    if fingerprint_dict and len(fingerprint_dict) > 0:
        ctx["fingerprint_version"] = "persona_v4"

        # Store compact behavior deck for runtime turn director
        moves = fingerprint_dict.get("conversation_moves", [])
        if moves:
            ctx["behavior_deck"] = [
                {
                    "move_id": m.get("move_id", ""),
                    "kind": m.get("kind", ""),
                    "instruction": m.get("instruction", ""),
                    "weight": m.get("weight", 1),
                }
                for m in moves
            ]

        # Store voice controls for potential runtime use
        vc = fingerprint_dict.get("voice_controls")
        if vc:
            ctx["voice_controls"] = vc

    return ctx


def prompt_record_to_db_row(
    animal_id: str,
    system_prompt: str,
    source_record_hash: str,
    render_context: dict,
    validation: dict,
    prompt_version: str = "v3",
) -> dict:
    """Canonical serializer for the system_prompts_v2 table."""
    return {
        "animal_id": animal_id,
        "prompt_version": prompt_version,
        "source_record_hash": source_record_hash,
        "system_prompt": system_prompt,
        "render_context_jsonb": render_context,
        "validation_results_jsonb": validation,
        "is_active": True,
    }
