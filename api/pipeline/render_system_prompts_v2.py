import os
import logging
from typing import Dict, Any

def render_system_prompt(fact_profile: Dict[str, Any], persona_profile: Dict[str, Any]) -> str:
    """
    Deterministically renders the final dog_system_prompt_v2.txt using
    facts and persona data. No LLM call is made here.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # We use the existing systemPromptTemplate.txt but with new V3 placeholders
    template_path = os.path.join(base_dir, "../../app/systemPromptTemplate.txt")
    if not os.path.exists(template_path):
        # Fallback if running from a different directory
        template_path = os.path.join(base_dir, "../../../app/systemPromptTemplate.txt")
        if not os.path.exists(template_path):
            raise RuntimeError("Could not find systemPromptTemplate.txt")
            
    with open(template_path, "r") as f:
        prompt_template = f.read()

    # Format lists into bullet points
    def to_bullets(items):
        if not items:
            return "- None noted."
        if isinstance(items, list):
            return "\n".join([f"- {item}" for item in items])
        return str(items)

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
        "LOCATION_DETAIL": fact_profile.get("location_detail", "None"),
        "ADOPTION_URL": fact_profile.get("adoption_url", ""),
        "IMAGE_URL": fact_profile.get("shelter_image_url", ""),
        
        # Archetype Style Rules
        "ARCHETYPE_CHARACTERS": persona_profile.get("characters", "* A good dog"),
        "ARCHETYPE_LINGUISTIC_STYLE": persona_profile.get("linguistic_style", "* Normal conversational tone"),
        
        # Facts
        "BACKSTORY_SUMMARY": fact_profile.get("backstory_summary", ""),
        "IMPORTANT_FACTS_BULLET_LIST": to_bullets(fact_profile.get("important_facts_jsonb", [])),
        "STRENGTHS": to_bullets(fact_profile.get("strengths_jsonb", [])),
        "CHALLENGES": to_bullets(fact_profile.get("challenges_jsonb", [])),
        "IDEAL_HOME": to_bullets(fact_profile.get("ideal_home_jsonb", [])),
        "MANAGEMENT_NOTES": to_bullets(fact_profile.get("management_notes_jsonb", [])),
        "DOG_CAT_OR_OTHER_ANIMAL_NOTES": fact_profile.get("other_animals_notes", ""),
        "PEOPLE_NOTES": fact_profile.get("people_notes", ""),
        "CONTAINMENT_NOTES": fact_profile.get("containment_notes", ""),
        "MEDICAL_NOTES": fact_profile.get("medical_notes", ""),
        "ADOPTION_PROCESS_NOTES": fact_profile.get("adoption_process_notes", ""),
        "FULL_BIO": fact_profile.get("full_bio", ""),
        "FULL_DESCRIPTION": fact_profile.get("full_description", ""),
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
        import re
        unreplaced = re.findall(r'\{[A-Z_]+\}', prompt)
        if unreplaced:
            errors.append(f"Unreplaced placeholders found: {unreplaced}")
            
    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }
