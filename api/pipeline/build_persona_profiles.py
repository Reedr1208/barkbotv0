import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class ArchetypeSelection(BaseModel):
    archetype_key: str = Field(description="The key of the chosen archetype")
    reasoning: str = Field(description="Brief explanation of why this archetype was chosen based on the animal's facts and the archetype's evidence criteria.")

def build_persona_profile(openai_client: OpenAI, fact_profile: dict, archetypes: list) -> dict:
    """
    Calls OpenAI to select the most fitting archetype based on the animal's facts and the archetype evidence criteria.
    """
    archetypes_context = []
    for arch in archetypes:
        archetypes_context.append({
            "archetype_key": arch["archetype_key"],
            "name": arch["name"],
            "evidence_criteria": arch["evidence_criteria"]
        })

    developer_prompt = (
        "You are an expert animal behavior analyst and creative writer. "
        "Your task is to review an animal's factual profile and select the SINGLE most appropriate persona archetype "
        "from the provided catalog. You must base your decision STRICTLY on the 'evidence_criteria' provided for each archetype."
    )

    user_prompt = (
        f"ANIMAL FACT PROFILE:\n{json.dumps(fact_profile, indent=2)}\n\n"
        f"AVAILABLE ARCHETYPES:\n{json.dumps(archetypes_context, indent=2)}\n\n"
        "Analyze the animal's facts and choose the archetype whose evidence criteria best matches the animal. "
        "Return the exact archetype_key and a brief reasoning."
    )

    logging.info(f"Selecting archetype for {fact_profile.get('animal_id')}...")
    
    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=ArchetypeSelection
    )
    
    parsed = response.choices[0].message.parsed
    
    # Find chosen archetype to include characters and linguistic_style
    chosen_arch = next((a for a in archetypes if a["archetype_key"] == parsed.archetype_key), None)
    
    return {
        "animal_id": fact_profile.get("animal_id"),
        "primary_archetype_key": parsed.archetype_key,
        "selection_reasoning": parsed.reasoning,
        "characters": chosen_arch["characters"] if chosen_arch else "",
        "linguistic_style": chosen_arch["linguistic_style"] if chosen_arch else "",
        "schema_version": "persona_v3",
        "scoring_model": "gpt-4o-mini",
        "scoring_params_jsonb": {"temperature": 0.4}
    }
