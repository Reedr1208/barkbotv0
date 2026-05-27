import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class FactorScoreDetails(BaseModel):
    score: int = Field(description="Score from 1 to 5")
    confidence: float = Field(description="Confidence from 0.0 to 1.0")
    evidence: str = Field(description="Short quote or evidence from facts justifying the score")

class PersonaScoringExtraction(BaseModel):
    energy: FactorScoreDetails
    social_confidence: FactorScoreDetails
    affection_drive: FactorScoreDetails
    goofiness: FactorScoreDetails
    cleverness: FactorScoreDetails
    sass: FactorScoreDetails
    rationale: str = Field(description="Brief rationale for the overall scores.")
    persona_summary: str = Field(description="One sentence summary of this dog's vibe.")

def calculate_distance(dog_scores: dict, archetype_scores: dict, salience_weights: dict) -> float:
    """Calculates weighted Manhattan distance between dog scores and archetype centroids."""
    distance = 0.0
    for factor in dog_scores:
        weight = salience_weights.get(factor, 1.0)
        dist = abs(dog_scores[factor] - archetype_scores.get(factor, 3))
        distance += weight * dist
    return distance

def compute_salience(scores: dict) -> dict:
    """Returns weights based on how far from neutral (3) a score is."""
    weights = {}
    for k, v in scores.items():
        # Distance from 3. If score is 1 or 5, weight is 2. If 2 or 4, weight is 1. If 3, weight is 0.5.
        diff = abs(v - 3)
        weights[k] = max(0.5, float(diff))
    return weights

def build_persona_profile(openai_client: OpenAI, fact_profile: dict, factor_catalog: list, archetypes: list, overrides: dict = None) -> dict:
    """
    Calls OpenAI to score the 6 factors, then uses deterministic logic to pick archetypes and merge styles.
    """
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    with open(os.path.join(base_dir, "prompts/persona_scoring_developer_prompt.txt"), "r") as f:
        developer_prompt = f.read()
        
    with open(os.path.join(base_dir, "prompts/persona_scoring_user_prompt.txt"), "r") as f:
        user_prompt_template = f.read()

    runtime_config = {
        "max_salient_factors": 3,
        "allow_secondary_archetype": True
    }

    user_prompt = user_prompt_template.format(
        FACTOR_DEFINITION_CATALOG_JSON=json.dumps(factor_catalog),
        ANIMAL_FACT_PROFILE_JSON=json.dumps(fact_profile),
        ANIMAL_PERSONA_OVERRIDE_JSON=json.dumps(overrides or {}),
        PERSONA_RUNTIME_CONFIG_JSON=json.dumps(runtime_config)
    )

    logging.info(f"Scoring persona for {fact_profile.get('animal_id')}...")
    
    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=PersonaScoringExtraction
    )
    
    parsed = response.choices[0].message.parsed
    
    # Extract raw scores
    dog_scores = {
        "energy": parsed.energy.score,
        "social_confidence": parsed.social_confidence.score,
        "affection_drive": parsed.affection_drive.score,
        "goofiness": parsed.goofiness.score,
        "cleverness": parsed.cleverness.score,
        "sass": parsed.sass.score
    }
    
    # Calculate salience
    salience_weights = compute_salience(dog_scores)
    
    # Find salient factors (those with highest diff from 3)
    sorted_factors = sorted(dog_scores.items(), key=lambda x: abs(x[1]-3), reverse=True)
    salient_factors = {k: v for k, v in sorted_factors if abs(v-3) >= 1}
    
    # Match archetypes
    best_distance = float('inf')
    primary_archetype = None
    
    for arch in archetypes:
        dist = calculate_distance(dog_scores, arch["centroid_scores_jsonb"], salience_weights)
        if dist < best_distance:
            best_distance = dist
            primary_archetype = arch
            
    # Merge styles
    voice_rules = {}
    
    # 1. Base rules from salient factors
    for factor_key, score in salient_factors.items():
        # Find factor in catalog
        factor_def = next((f for f in factor_catalog if f["factor_key"] == factor_key), None)
        if factor_def:
            rules = factor_def["style_rules_by_score_jsonb"].get(str(score), {})
            voice_rules.update(rules)
            
    # 2. Archetype overrides
    if primary_archetype:
        voice_rules.update(primary_archetype.get("style_overrides_jsonb", {}))
        
    return {
        "animal_id": fact_profile.get("animal_id"),
        "factor_scores_jsonb": dog_scores,
        "salient_factors_jsonb": salient_factors,
        "primary_archetype_key": primary_archetype["archetype_key"] if primary_archetype else None,
        "secondary_archetype_key": None,
        "variant_key": None,
        "persona_summary": parsed.persona_summary,
        "voice_rules_jsonb": voice_rules,
        "style_examples_jsonb": primary_archetype.get("example_lines_jsonb", []) if primary_archetype else [],
        "opening_disclosure_line": "Some of my vibe here is inferred from my shelter notes, but I'm trying to be my true self!",
        "persona_guardrails_jsonb": {},
        "schema_version": "persona_v1",
        "scoring_model": "gpt-4o-mini",
        "scoring_params_jsonb": {"temperature": 0.7},
        "override_applied": False
    }
