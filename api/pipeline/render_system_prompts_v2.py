"""
System prompt renderer — deterministic template fill, no LLM call.

Supports both v3 (archetype characters/style) and v4 (persona fingerprint)
personas. When a v4 fingerprint is present, it renders the PERSONA_V4_BLOCK
with dog-specific identity dimensions. When absent, falls back to v3 style.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("barkbot.pipeline.renderer")


def render_system_prompt(fact_profile: Dict[str, Any], persona_profile: Dict[str, Any], fingerprint_dict: Optional[dict] = None) -> str:
    """
    Deterministically renders the system prompt using facts, persona, and
    optionally a v4 fingerprint.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))

    template_path = os.path.join(base_dir, "../../app/systemPromptTemplate.txt")
    if not os.path.exists(template_path):
        template_path = os.path.join(base_dir, "../../../app/systemPromptTemplate.txt")
        if not os.path.exists(template_path):
            raise RuntimeError("Could not find systemPromptTemplate.txt")

    with open(template_path, "r") as f:
        prompt_template = f.read()

    # Build the v4 persona block (or v3 fallback)
    persona_v4_block = _render_persona_block(persona_profile, fingerprint_dict)

    # Build behavior/needs block (only populated sections)
    behavior_needs_block = _render_behavior_needs(fact_profile)

    # Prepare context
    context = {
        "DOG_NAME": fact_profile.get("dog_name", "Buddy"),
        "ANIMAL_ID": fact_profile.get("animal_id", ""),
        "AGE": fact_profile.get("age_summary", "Unknown age"),
        "WEIGHT": fact_profile.get("weight_summary", "Unknown weight"),
        "BREED_OR_DESCRIPTION": fact_profile.get("breed_or_description", "Mixed breed"),
        "SEX": fact_profile.get("sex", "Unknown"),
        "ALTERED_STATUS": fact_profile.get("altered_status", "Unknown"),
        "LOCATION_SUMMARY": fact_profile.get("shelter_name", "Unknown"),
        "LOCATION_DETAIL": fact_profile.get("location_detail", ""),
        "ADOPTION_URL": fact_profile.get("adoption_url", ""),
        "IMAGE_URL": fact_profile.get("shelter_image_url", ""),

        # Persona block
        "PERSONA_V4_BLOCK": persona_v4_block,

        # Facts
        "BACKSTORY_SUMMARY": fact_profile.get("backstory_summary", ""),
        "IMPORTANT_FACTS_BULLET_LIST": _to_bullets(fact_profile.get("important_facts_jsonb", [])),
        "BEHAVIOR_NEEDS_BLOCK": behavior_needs_block,
        "FULL_BIO": fact_profile.get("full_bio", ""),
        "FULL_DESCRIPTION": fact_profile.get("full_description", ""),
    }

    # Replace placeholders
    prompt = prompt_template
    for key, value in context.items():
        safe_value = value if value is not None else ""
        prompt = prompt.replace("{" + key + "}", str(safe_value))

    return prompt


def _to_bullets(items) -> str:
    """Format list items as bullets. Empty lists produce empty string (not 'None noted')."""
    if not items:
        return ""
    if isinstance(items, list):
        non_empty = [item for item in items if item]
        if not non_empty:
            return ""
        return "\n".join([f"- {item}" for item in non_empty])
    return str(items)


def _render_persona_block(persona_profile: dict, fingerprint_dict: Optional[dict] = None) -> str:
    """
    Render the PERSONA_V4_BLOCK placeholder.
    v4: Full fingerprint-based identity.
    v3 fallback: Archetype characters + linguistic style.
    """
    if fingerprint_dict and fingerprint_dict.get("archetype_expression"):
        return _render_v4_block(fingerprint_dict)
    else:
        return _render_v3_block(persona_profile)


def _render_v3_block(persona_profile: dict) -> str:
    """V3 fallback: archetype characters and linguistic style."""
    characters = persona_profile.get("characters", "* A good dog")
    linguistic_style = persona_profile.get("linguistic_style", "* Normal conversational tone")

    return (
        f"VOICE INSPIRATION\n"
        f"Channel the energy and vibe of these characters:\n"
        f"{characters}\n\n"
        f"LINGUISTIC STYLE RULES\n"
        f"Your baseline style will always be to misspell certain words and choose doggo-specific vocabulary in a childlike, playful way.\n"
        f"Strictly adhere to the additional rules below to build on this baseline:\n\n"
        f"{linguistic_style}\n\n"
        f"- Keep responses concise but not so extreme that important facts become unclear.\n"
        f"- Serious adoption or safety information should be clear."
    )


def _render_v4_block(fp: dict) -> str:
    """V4: Render persona fingerprint into structured identity block."""
    sections = []

    # Core identity
    sections.append("YOUR IDENTITY")
    sections.append(f"Archetype expression: {fp.get('archetype_expression', '')}")
    sections.append(f"Core motive: {fp.get('core_motive', '')}")
    sections.append(f"Social posture: {fp.get('social_posture', '')}")
    sections.append(f"Contrast trait: {fp.get('contrast_trait', '')}")

    # Attention biases
    biases = fp.get("attention_biases", [])
    if biases:
        sections.append("")
        sections.append("WHAT YOU NOTICE FIRST")
        for b in biases:
            sections.append(f"- {b}")

    # Humor engine
    humor = fp.get("humor_engine")
    if humor:
        sections.append("")
        sections.append(f"HOW YOU CREATE HUMOR\n{humor}")

    # Imagination lenses
    lenses = fp.get("imagination_lenses", [])
    if lenses:
        sections.append("")
        sections.append("YOUR IMAGINATION TENDS TOWARD")
        for l in lenses:
            sections.append(f"- {l}")

    # Voice controls
    vc = fp.get("voice_controls", {})
    if vc:
        sections.append("")
        sections.append("VOICE CONTROLS")
        sections.append(f"Energy: {vc.get('energy', 3)}/5")
        sections.append(f"Warmth: {vc.get('warmth', 3)}/5")
        sections.append(f"Boldness: {vc.get('boldness', 3)}/5")
        sections.append(f"Absurdity: {vc.get('absurdity', 2)}/5")
        sections.append(f"Doggo slang: {vc.get('doggo_slang', 3)}/5")
        sections.append(f"Emoji density: {vc.get('emoji_density', 2)}/5")
        sections.append(f"Rhythm: {vc.get('rhythm', 'natural')}")
        sections.append(f"Diction: {vc.get('diction', 'conversational')}")

    # Relationship arc
    arc = fp.get("relationship_arc", {})
    if arc:
        sections.append("")
        sections.append("HOW YOUR VOICE DEVELOPS")
        if arc.get("first_contact"):
            sections.append(f"First contact: {arc['first_contact']}")
        if arc.get("warming"):
            sections.append(f"Warming up: {arc['warming']}")
        if arc.get("comfortable"):
            sections.append(f"Comfortable: {arc['comfortable']}")

    # Anti-patterns
    anti = fp.get("anti_patterns", [])
    if anti:
        sections.append("")
        sections.append("TENDENCIES TO AVOID")
        for a in anti:
            sections.append(f"- {a}")

    return "\n".join(sections)


def _render_behavior_needs(fact_profile: dict) -> str:
    """
    Render behavior/needs sections, omitting empty ones entirely.
    Prevents "- None noted." from appearing as a confirmed absence.
    """
    sections = []

    _add_section(sections, "Known sensitivities or challenges:", fact_profile.get("challenges_jsonb", []))
    _add_section(sections, "Handling / introductions / management notes:", fact_profile.get("management_notes_jsonb", []))

    # Text fields — only include if they have content
    _add_text_section(sections, "Other animals:", fact_profile.get("other_animals_notes"))
    _add_text_section(sections, "People / strangers / guests:", fact_profile.get("people_notes"))
    _add_text_section(sections, "Containment / yard / escape notes:", fact_profile.get("containment_notes"))
    _add_text_section(sections, "Medical notes:", fact_profile.get("medical_notes"))
    _add_text_section(sections, "Adoption process notes:", fact_profile.get("adoption_process_notes"))

    return "\n\n".join(sections) if sections else ""


def _add_section(sections: list, header: str, items) -> None:
    """Add a bullet-list section only if items exist."""
    bullets = _to_bullets(items)
    if bullets:
        sections.append(f"{header}\n{bullets}")


def _add_text_section(sections: list, header: str, text: Optional[str]) -> None:
    """Add a text section only if text has content."""
    if text and text.strip():
        sections.append(f"{header}\n{text.strip()}")


def validate_system_prompt(prompt: str) -> dict:
    """
    Validates that the rendered prompt doesn't have missing placeholders or formatting issues.
    """
    errors = []
    if "{" in prompt and "}" in prompt:
        unreplaced = re.findall(r'\{[A-Z_]+\}', prompt)
        if unreplaced:
            errors.append(f"Unreplaced placeholders found: {unreplaced}")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }
