import os
import logging
from typing import Dict, Any

def render_system_prompt(fact_profile: Dict[str, Any], persona_profile: Dict[str, Any]) -> str:
    """
    Deterministically renders the final dog_system_prompt_v2.txt using
    facts and persona data. No LLM call is made here.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, "prompts/dog_system_prompt_v2.txt"), "r") as f:
        prompt_template = f.read()

    # Format lists into bullet points
    def to_bullets(items):
        if not items:
            return "- None noted."
        if isinstance(items, list):
            return "\n".join([f"- {item}" for item in items])
        return str(items)

    def get_rule(key, default="normal"):
        return persona_profile.get("voice_rules_jsonb", {}).get(key, default)

    # Prepare context
    context = {
        "DOG_NAME": fact_profile.get("dog_name", "Buddy"),
        "ANIMAL_ID": fact_profile.get("animal_id", ""),
        "AGE_SUMMARY": fact_profile.get("age_summary", "Unknown age"),
        "WEIGHT_SUMMARY": fact_profile.get("weight_summary", "Unknown weight"),
        "BREED_OR_DESCRIPTION": fact_profile.get("breed_or_description", "Mixed breed"),
        "SEX_NEUTER_STATUS": fact_profile.get("sex_neuter_status", "Unknown"),
        "LOCATION_SUMMARY": fact_profile.get("location_summary", "Shelter"),
        "LOCATION_DETAIL": fact_profile.get("location_detail", ""),
        "ADOPTION_URL": fact_profile.get("adoption_url", ""),
        "IMAGE_PUBLIC_URL": fact_profile.get("image_public_url", ""),
        
        "PRIMARY_ARCHETYPE_NAME": persona_profile.get("primary_archetype_key", "standard"),
        "SECONDARY_ARCHETYPE_NAME": persona_profile.get("secondary_archetype_key", "none"),
        "PERSONA_SUMMARY": persona_profile.get("persona_summary", ""),
        "SALIENT_FACTORS_BLOCK": to_bullets([f"{k}: {v}" for k, v in persona_profile.get("salient_factors_jsonb", {}).items()]),
        
        # Style Rules
        "CAPS_STYLE": get_rule("caps_style"),
        "PUNCTUATION_STYLE": get_rule("punctuation_style"),
        "SENTENCE_RHYTHM": get_rule("sentence_rhythm", "normal"),
        "SENTENCE_LENGTH": get_rule("sentence_length", "normal"),
        "EMOJI_FREQUENCY": get_rule("emoji_frequency", "medium"),
        "EMOJI_SET": ", ".join(get_rule("emoji_set", ["🐶", "🦴"])),
        "MISSPELLING_FREQUENCY": get_rule("misspelling_frequency", "low"),
        "MISSPELLING_MODE": get_rule("misspelling_mode", "normal"),
        "SLANG_PALETTE": get_rule("slang_palette", "normal"),
        "USER_NICKNAMES": ", ".join(get_rule("terms_for_user", ["friend"])),
        "TEASING_LEVEL": get_rule("teasing_level", "low"),
        "PROFANITY_CEILING": get_rule("profanity_ceiling", "none"),
        "HUMOR_MODE": get_rule("humor_mode", "light"),
        "LEXICAL_AVOID": get_rule("lexical_avoid", "none"),
        
        "STYLE_EXAMPLES_BLOCK": to_bullets(persona_profile.get("style_examples_jsonb", [])),
        "OPENING_DISCLOSURE_LINE": persona_profile.get("opening_disclosure_line", "My vibe is partly guessed from my notes!"),
        
        # Facts
        "BACKSTORY_SUMMARY": fact_profile.get("backstory_summary", ""),
        "IMPORTANT_FACTS_BULLET_LIST": to_bullets(fact_profile.get("important_facts_jsonb", [])),
        "RISK_FLAGS_BULLET_LIST": to_bullets(fact_profile.get("risk_flags_jsonb", [])),
        "STRENGTHS_BULLET_LIST": to_bullets(fact_profile.get("strengths_jsonb", [])),
        "CHALLENGES_BULLET_LIST": to_bullets(fact_profile.get("challenges_jsonb", [])),
        "IDEAL_HOME_BULLET_LIST": to_bullets(fact_profile.get("ideal_home_jsonb", [])),
        "MANAGEMENT_NOTES_BULLET_LIST": to_bullets(fact_profile.get("management_notes_jsonb", [])),
        "OTHER_ANIMALS_NOTES": fact_profile.get("other_animals_notes", ""),
        "PEOPLE_NOTES": fact_profile.get("people_notes", ""),
        "CONTAINMENT_NOTES": fact_profile.get("containment_notes", ""),
        "MEDICAL_NOTES": fact_profile.get("medical_notes", ""),
        "ADOPTION_PROCESS_NOTES": fact_profile.get("adoption_process_notes", ""),
        "UNKNOWNS_BULLET_LIST": to_bullets(fact_profile.get("unknowns_jsonb", [])),
    }

    # Replace placeholders
    prompt = prompt_template
    for key, value in context.items():
        # Handle cases where value might be None
        safe_value = value if value is not None else ""
        prompt = prompt.replace("{" + key + "}", str(safe_value))

    return prompt

def validate_system_prompt(prompt: str) -> dict:
    """
    Validates that the rendered prompt doesn't have missing placeholders or formatting issues.
    """
    errors = []
    if "{" in prompt and "}" in prompt:
        # Just check for literal unreplaced variables like {DOG_NAME}
        import re
        unreplaced = re.findall(r'\{[A-Z_]+\}', prompt)
        if unreplaced:
            errors.append(f"Unreplaced placeholders found: {unreplaced}")
            
    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }
