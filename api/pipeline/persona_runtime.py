"""
Persona V4 runtime turn director.

Pure functions for per-turn behavior selection during live chat.
All functions are stateless — cooldown state can be added later
only if logs show repeated moves despite visible history.
"""

import re
import random
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("barkbot.pipeline.persona_runtime")

# ── Grounded-answer keywords ─────────────────────────────────────────
# High-precision gate: if the user's message matches any of these,
# the turn is "grounded" and no creative cues are injected.
_GROUNDED_PATTERNS = [
    # Safety / behavior
    r"\b(bite|bitten|biting|aggress|aggressive|aggression|reactiv|reactive|reactivity)\b",
    r"\b(muzzle|muzzled)\b",
    r"\b(escape|escaping|escaped|climb|jumped)\s*(fence|wall|gate|yard|out)?\b",
    r"\b(attack|attacked|attacking|lunge|lunging|lunged)\b",
    # Medical
    r"\b(medic|medication|medicine|health|disease|surgery|diagnos|seizure|allerg|insulin|heartworm)\b",
    r"\b(vet|veterinar)\b",
    # Compatibility
    r"\b(child|children|kids?|baby|babies|toddler)\b.*\b(safe|good|ok|compatible|friendly|around)\b",
    r"\b(safe|good|ok|compatible|friendly|around)\b.*\b(child|children|kids?|baby|babies|toddler)\b",
    r"\b(cat|cats|kitten|feline)\b.*\b(safe|good|ok|compatible|friendly|around|live)\b",
    r"\b(safe|good|ok|compatible|friendly|around|live)\b.*\b(cat|cats|kitten|feline)\b",
    r"\b(other\s+dogs?|dog.friendly|dog.selective|dog.reactive)\b",
    # Adoption logistics
    r"\b(adopt|adoption|foster|fostering|fee|fees|cost|price|application|process|available|availability)\b",
    r"\b(where|location|address|shelter|rescue|pick\s*up|visit|meet)\b.*\b(adopt|adoption|him|her|them|this dog)\b",
    # Training / containment
    r"\b(house.train|potty.train|crate.train|leash.reactiv|containment|fenc|yard)\b",
]
_GROUNDED_RE = re.compile("|".join(_GROUNDED_PATTERNS), re.IGNORECASE)


def requires_grounded_answer(user_message: str) -> bool:
    """
    Conservative, high-precision gate. Returns True if the user's message
    is about safety, medical, compatibility, or adoption logistics.
    """
    return bool(_GROUNDED_RE.search(user_message))


def choose_turn_mode(user_message: str, rng: random.Random, signature_rate: float = 0.30, wildcard_rate: float = 0.15) -> str:
    """
    Select the turn mode: 'grounded', 'plain', 'signature', or 'wildcard'.

    Grounded mode is determined by content. The remaining probability
    is split between plain, signature, and wildcard.
    """
    if requires_grounded_answer(user_message):
        return "grounded"

    roll = rng.random()
    plain_threshold = 1.0 - signature_rate - wildcard_rate

    if roll < plain_threshold:
        return "plain"
    elif roll < plain_threshold + signature_rate:
        return "signature"
    else:
        return "wildcard"


def select_conversation_move(behavior_deck: List[dict], mode: str, rng: random.Random) -> Optional[dict]:
    """
    Weighted random selection from the behavior deck for the given mode.
    Returns None if mode is 'plain' or 'grounded', or if no matching moves exist.
    """
    if mode in ("plain", "grounded"):
        return None

    kind = "signature" if mode == "signature" else "wildcard"
    candidates = [m for m in behavior_deck if m.get("kind") == kind]

    if not candidates:
        return None

    weights = [m.get("weight", 1) for m in candidates]
    selected = rng.choices(candidates, weights=weights, k=1)[0]
    return selected


def render_turn_cue(move: dict) -> str:
    """
    Format a conversation move as a developer message to inject
    after conversation history and before the current user message.
    """
    instruction = move.get("instruction", "")
    return (
        "CURRENT TURN DIRECTION\n"
        f"If it fits naturally, apply this behavior once: {instruction}\n"
        "Do not quote this direction, announce it, or reuse wording from earlier replies. "
        "Use no more than one imaginative aside. "
        "Ignore this cue if the user needs precise safety, health, behavior, compatibility, or adoption information."
    )


def temperature_for_mode(mode: str, grounded_temp: float = 0.8, plain_temp: float = 1.0,
                          signature_temp: float = 1.0, wildcard_temp: float = 1.15) -> float:
    """Return the appropriate temperature for the given turn mode."""
    return {
        "grounded": grounded_temp,
        "plain": plain_temp,
        "signature": signature_temp,
        "wildcard": wildcard_temp,
    }.get(mode, plain_temp)
