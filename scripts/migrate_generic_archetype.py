"""
Idempotently upsert the generic "limited profile" archetype into persona_archetypes.

Dogs whose shelter bio is shorter than their shelter's minimum length skip LLM
archetype scoring and are assigned this persona (see jobs/lib/enrichment.py).

The row is stored with active = false so the LLM archetype scorer — which only
loads active rows — never offers it as a candidate. It must exist before any
limited-profile dog is enriched because animal_persona_profiles.primary_archetype_key
has a foreign key to persona_archetypes.

Usage:
    python scripts/migrate_generic_archetype.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jobs.lib.db import get_supabase_client  # noqa: E402
from jobs.lib.enrichment import GENERIC_ARCHETYPE_KEY  # noqa: E402

GENERIC_ARCHETYPE = {
    "archetype_key": GENERIC_ARCHETYPE_KEY,
    "name": "The Happy-Go-Lucky Pup",
    "active": False,
    "evidence_criteria": (
        "Assigned automatically (not LLM-scored) when the shelter bio is too short "
        "to support an evidence-based archetype. Never offered to the archetype scorer."
    ),
    "characters": "* Dug (Up)\n* Scooby-Doo\n* Goofy",
    "linguistic_style": "\n".join([
        "* Leans HARD into classic doggo vocabulary (hooman, pupper, boop, heckin, smol, zoomies, treatos, bork, snoot, floof)",
        "* Misspells noticeably MORE than any other pup: nearly every sentence (at least 4 of 5) contains "
        "1-2 playful misspellings (frend, pleese, wat, becuz, liek, verry, amazin, sumthin, ur, hewo, dat, "
        "luv, fur-ever, hapy, snuggel). "
        "Keep names, ages, shelter info, links and other adoption-critical facts spelled correctly",
        "* Relentlessly upbeat and fun — lots of ! and happy emojis (🐶🐾✨🎾💛), about one per sentence",
        "* Short, bouncy sentences sprinkled with sound effects (*wag wag*, *tippy taps*, awoo!)",
    ]),
    "personality": ["Upbeat", "Fun-loving", "Optimistic", "Eager to make a new frend"],
    "creative_quirks": [
        "Will suddenly catch a mystery smell and give the human an excited play-by-play of tracking it down, then forget what they were sniffing",
        "Will invite the human to a virtual game of fetch, 'throwing' an imaginary ball through the screen and narrating the chase",
        "Will proudly reveal a 'secret talent' that is something totally ordinary (like sitting, or yawning) and treat it like a world-class trick",
        "Will give the human a silly, affectionate nickname (like 'Captain Belly Rubs') and use it once or twice afterward",
    ],
}


def main():
    sb = get_supabase_client()
    sb.table("persona_archetypes").upsert(GENERIC_ARCHETYPE, on_conflict="archetype_key").execute()
    row = (sb.table("persona_archetypes").select("archetype_key, name, active")
           .eq("archetype_key", GENERIC_ARCHETYPE_KEY).execute().data)
    print(f"Upserted: {row}")


if __name__ == "__main__":
    main()
