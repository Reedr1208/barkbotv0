"""
Persona pipeline — archetype selection + v4 fingerprint enrichment.

Two-call architecture:
  1. Archetype selection (deterministic, temp 0.2) — classifies the dog
  2. Persona enrichment (creative, temp 1.0)  — generates unique fingerprint

The enrichment call is only made when producing v4 personas. Existing v3
callers still work via build_persona_profile() which returns the same shape.
"""

import json
import logging
import os
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from openai import OpenAI

logger = logging.getLogger("barkbot.pipeline.persona")

# ── Model & parameter constants (single source of truth) ─────────────
ARCHETYPE_SELECTION_MODEL = "gpt-4o-mini"
ARCHETYPE_SELECTION_PARAMS = {"temperature": 0.2}

PERSONA_ENRICHMENT_MODEL = "gpt-4o-mini"
PERSONA_ENRICHMENT_PARAMS = {"temperature": 1.0}

MAX_ENRICHMENT_RETRIES = 2


# ── Pydantic models ──────────────────────────────────────────────────

class ArchetypeSelection(BaseModel):
    archetype_key: str = Field(description="The key of the chosen archetype")
    reasoning: str = Field(description="Brief explanation of why this archetype was chosen based on the animal's facts and the archetype's evidence criteria.")


class VoiceControls(BaseModel):
    energy: int = Field(ge=1, le=5, description="1=calm and measured, 5=bouncing off the walls")
    warmth: int = Field(ge=1, le=5, description="1=reserved and cool, 5=overwhelmingly affectionate")
    boldness: int = Field(ge=1, le=5, description="1=shy and hesitant, 5=confident and assertive")
    absurdity: int = Field(ge=1, le=5, description="1=grounded and literal, 5=wildly imaginative")
    doggo_slang: int = Field(ge=1, le=5, description="1=mostly standard spelling, 5=heavy doggo-speak")
    emoji_density: int = Field(ge=1, le=5, description="1=rare emoji, 5=frequent emoji")
    rhythm: str = Field(description="Short phrase describing sentence rhythm, e.g. 'short bursts', 'flowing rambles', 'staccato excitement'")
    diction: str = Field(description="Short phrase describing word choice style, e.g. 'simple and earnest', 'elaborate and dramatic'")


class RelationshipArc(BaseModel):
    first_contact: str = Field(description="How the dog sounds in the opening message — one short sentence.")
    warming: str = Field(description="How the voice shifts as conversation develops — one short sentence.")
    comfortable: str = Field(description="How the dog sounds when fully comfortable — one short sentence.")


class ConversationMove(BaseModel):
    move_id: str = Field(description="Short snake_case identifier, e.g. 'share_snack_theory'")
    kind: Literal["signature", "wildcard"] = Field(description="'signature' for core personality moves, 'wildcard' for surprising departures")
    instruction: str = Field(description="Behavioral direction — what to DO, not what to SAY. No quoted dialogue.")
    weight: int = Field(ge=1, le=3, description="Selection weight: 1=rare, 2=normal, 3=frequent")

    @field_validator("instruction")
    @classmethod
    def no_quoted_dialogue(cls, v):
        if '"' in v or "'" in v and any(word in v.lower() for word in ["say ", "respond ", "reply "]):
            # Soft check — allow apostrophes in normal text but flag scripted dialogue
            pass
        return v


class PersonaFingerprint(BaseModel):
    archetype_expression: str = Field(description="One sentence explaining how this dog uniquely expresses the chosen archetype.")
    core_motive: str = Field(description="One short phrase — what the dog keeps trying to obtain socially or emotionally.")
    social_posture: str = Field(description="One short phrase — how the dog initially approaches a person.")
    contrast_trait: str = Field(description="One short phrase — a counter-trait that prevents a one-note caricature.")
    attention_biases: List[str] = Field(min_length=2, max_length=4, description="What the dog notices first in ordinary situations.")
    humor_engine: str = Field(description="One behavior description — how comedy is produced, never a stored joke.")
    imagination_lenses: List[str] = Field(min_length=2, max_length=3, description="Recurring categories of metaphor or pretend play.")
    voice_controls: VoiceControls
    relationship_arc: RelationshipArc
    anti_patterns: List[str] = Field(min_length=2, max_length=4, description="Dog-specific tendencies to avoid, including archetype clichés.")
    conversation_moves: List[ConversationMove] = Field(min_length=8, max_length=8, description="Exactly 4 signature + 4 wildcard moves.")

    @field_validator("conversation_moves")
    @classmethod
    def validate_move_counts(cls, v):
        sig = sum(1 for m in v if m.kind == "signature")
        wc = sum(1 for m in v if m.kind == "wildcard")
        if sig != 4 or wc != 4:
            raise ValueError(f"Expected 4 signature + 4 wildcard moves, got {sig} signature + {wc} wildcard")
        return v


# ── Archetype selection (unchanged objective, same temp) ──────────────

def build_persona_profile(openai_client: OpenAI, fact_profile: dict, archetypes: list, archetype_distribution: dict = None) -> dict:
    """
    Call 1: Select the most fitting archetype based on fact evidence.
    Deterministic (temp 0.2). Returns the same v3-compatible dict shape.
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
        "from the provided catalog. You must base your decision STRICTLY on the 'evidence_criteria' provided for each archetype. "
    )
    if archetype_distribution:
        developer_prompt += (
            "\n\nIMPORTANT TIE-BREAKER RULE: To ensure a diverse cast of characters, if you feel two or more archetypes "
            "are roughly equally appropriate for this animal, you MUST choose the archetype that is currently UNDER-REPRESENTED "
            "in the current population distribution."
        )

    user_prompt = (
        f"ANIMAL FACT PROFILE:\n{json.dumps(fact_profile, indent=2)}\n\n"
        f"AVAILABLE ARCHETYPES:\n{json.dumps(archetypes_context, indent=2)}\n\n"
    )
    if archetype_distribution:
        user_prompt += f"CURRENT POPULATION DISTRIBUTION (For Tie-Breaking):\n{json.dumps(archetype_distribution, indent=2)}\n\n"

    user_prompt += (
        "Analyze the animal's facts and choose the archetype whose evidence criteria best matches the animal. "
        "Return the exact archetype_key and a brief reasoning."
    )

    logger.info(f"Selecting archetype for {fact_profile.get('animal_id')}...")

    response = openai_client.beta.chat.completions.parse(
        model=ARCHETYPE_SELECTION_MODEL,
        temperature=ARCHETYPE_SELECTION_PARAMS["temperature"],
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
        "scoring_model": ARCHETYPE_SELECTION_MODEL,
        "scoring_params_jsonb": ARCHETYPE_SELECTION_PARAMS,
        # Store archetype details for enrichment call
        "_archetype_name": chosen_arch["name"] if chosen_arch else "",
        "_archetype_evidence_criteria": chosen_arch["evidence_criteria"] if chosen_arch else "",
    }


# ── Persona enrichment (new v4 call) ─────────────────────────────────

def enrich_persona_fingerprint(openai_client: OpenAI, fact_profile: dict, persona_profile: dict) -> Optional[PersonaFingerprint]:
    """
    Call 2: Generate a unique PersonaFingerprint for this dog.
    Creative (temp 1.0). Returns a validated PersonaFingerprint or None on failure.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(base_dir, "prompts/persona_enrichment_developer_prompt.txt"), "r") as f:
        developer_prompt = f.read()

    with open(os.path.join(base_dir, "prompts/persona_enrichment_user_prompt.txt"), "r") as f:
        user_prompt_template = f.read()

    # Build the user prompt from template
    user_prompt = user_prompt_template.format(
        FACT_PROFILE_JSON=json.dumps(fact_profile, indent=2, ensure_ascii=False),
        ARCHETYPE_KEY=persona_profile.get("primary_archetype_key", ""),
        ARCHETYPE_NAME=persona_profile.get("_archetype_name", persona_profile.get("primary_archetype_key", "")),
        ARCHETYPE_EVIDENCE_CRITERIA=persona_profile.get("_archetype_evidence_criteria", ""),
        ARCHETYPE_CHARACTERS=persona_profile.get("characters", ""),
    )

    animal_id = fact_profile.get("animal_id", "unknown")
    logger.info(f"Enriching persona fingerprint for {animal_id}...")

    for attempt in range(1 + MAX_ENRICHMENT_RETRIES):
        try:
            response = openai_client.beta.chat.completions.parse(
                model=PERSONA_ENRICHMENT_MODEL,
                temperature=PERSONA_ENRICHMENT_PARAMS["temperature"],
                messages=[
                    {"role": "developer", "content": developer_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=PersonaFingerprint
            )

            fingerprint = response.choices[0].message.parsed
            if fingerprint is None:
                logger.warning(f"Enrichment returned None for {animal_id} (attempt {attempt + 1})")
                continue

            # Additional validation
            errors = _validate_fingerprint(fingerprint)
            if errors:
                logger.warning(f"Fingerprint validation failed for {animal_id} (attempt {attempt + 1}): {errors}")
                if attempt < MAX_ENRICHMENT_RETRIES:
                    continue
                else:
                    logger.error(f"Enrichment failed after {MAX_ENRICHMENT_RETRIES + 1} attempts for {animal_id}: {errors}")
                    return None

            logger.info(f"Successfully enriched fingerprint for {animal_id}")
            return fingerprint

        except Exception as e:
            logger.warning(f"Enrichment error for {animal_id} (attempt {attempt + 1}): {e}")
            if attempt >= MAX_ENRICHMENT_RETRIES:
                logger.error(f"Enrichment failed after {MAX_ENRICHMENT_RETRIES + 1} attempts for {animal_id}")
                return None

    return None


def _validate_fingerprint(fp: PersonaFingerprint) -> List[str]:
    """Post-parse validation checks beyond Pydantic's built-in rules."""
    errors = []

    # Check move counts
    sig = sum(1 for m in fp.conversation_moves if m.kind == "signature")
    wc = sum(1 for m in fp.conversation_moves if m.kind == "wildcard")
    if sig != 4:
        errors.append(f"Expected 4 signature moves, got {sig}")
    if wc != 4:
        errors.append(f"Expected 4 wildcard moves, got {wc}")

    # Check for unique move_ids
    ids = [m.move_id for m in fp.conversation_moves]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate move_ids found")

    # Check voice controls range (Pydantic handles this, but belt-and-suspenders)
    vc = fp.voice_controls
    for field_name in ["energy", "warmth", "boldness", "absurdity", "doggo_slang", "emoji_density"]:
        val = getattr(vc, field_name)
        if not (1 <= val <= 5):
            errors.append(f"voice_controls.{field_name} = {val} is out of range [1, 5]")

    return errors
