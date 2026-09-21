"""
Feature flags for the Persona V4 system.

All flags are read from environment variables with sensible defaults.
Set PERSONA_V4_ENABLED=true to activate v4 fingerprint rendering.
Set PERSONA_TURN_DIRECTOR_ENABLED=true to activate per-turn cue injection.
"""

import os


def _bool_env(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


# ── Core v4 flag ──────────────────────────────────────────────────────
PERSONA_V4_ENABLED = _bool_env("PERSONA_V4_ENABLED", False)

# ── Runtime turn director ─────────────────────────────────────────────
PERSONA_TURN_DIRECTOR_ENABLED = _bool_env("PERSONA_TURN_DIRECTOR_ENABLED", False)

# ── Turn mode probabilities ───────────────────────────────────────────
PERSONA_SIGNATURE_RATE = _float_env("PERSONA_SIGNATURE_RATE", 0.30)
PERSONA_WILDCARD_RATE = _float_env("PERSONA_WILDCARD_RATE", 0.15)

# ── Temperature controls ──────────────────────────────────────────────
PERSONA_GROUNDED_TEMPERATURE = _float_env("PERSONA_GROUNDED_TEMPERATURE", 0.8)
PERSONA_PLAIN_TEMPERATURE = _float_env("PERSONA_PLAIN_TEMPERATURE", 1.0)
PERSONA_SIGNATURE_TEMPERATURE = _float_env("PERSONA_SIGNATURE_TEMPERATURE", 1.0)
PERSONA_WILDCARD_TEMPERATURE = _float_env("PERSONA_WILDCARD_TEMPERATURE", 1.15)
