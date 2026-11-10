"""
BDW (Bideawee, New York NY) — Profile Scraper

Bideawee's profile pages (/adopt-pet/{slug}/{Internal-ID}) are rendered
client-side, so instead of scraping HTML we read the same Shelterluv v1 record
the page uses:

    GET https://www.shelterluv.com/api/v1/animals/{Internal-ID}

The bio is assembled from structured fields (breed, sex, age, weight, size,
color, location, published behaviour/medical attributes, adoption fee) followed
by the narrative Description with Bideawee's repeated adoption-process
boilerplate removed (that info lives in shelters.process_details instead).

Non-dogs raise NOT_A_DOG (removed everywhere by the shared runner); dogs the
site now shows as adopted are dropped from active_dogs.

No Playwright needed. Runs via APScheduler using the shared profiles_runner.
"""

import html
import json
import logging
import re
import sys
from typing import Any, Dict, List

import requests

from jobs.lib.profiles_runner import run_profiles_scrape
from jobs.shelters.bdw.inventory import (
    ADOPTED_ATTRIBUTE,
    CITY,
    HEADERS,
    SHELTER_ID,
    SHELTER_NAME,
    STATE,
    attribute_names,
    clean_name,
    fetch_animal,
    format_age,
    format_weight,
    profile_url,
)

# One small JSON request per dog — the ~20-dog roster refreshes in ~2 runs.
DOGS_PER_RUN = 10
RUNNER_SLEEP_SECONDS = 2.0

# Internal / staff-only attributes that shouldn't reach the bio even if published.
INTERNAL_ATTRIBUTES_RE = re.compile(
    r"waiver|medical discharge|special disclaimer|adopted for gallery|currently contagious", re.I
)

# Sentences Bideawee repeats across (nearly) every description. They describe
# the adoption process / location logistics, not the dog.
BOILERPLATE_SENTENCE_RE = re.compile(
    r"same[- ]day adoption"
    r"|application does not put you on a list"
    r"|prior to adoption, all of our animals"
    r"|spayed/neutered,? microchipped"
    r"|in wantagh or in a foster home"
    r"|located at our (?:manhattan|westhampton|wantagh) adoption center"
    r"|view our adoption process"
    r"|viewing this animal on petfinder"
    r"|click \W?apply for adoption"
    r"|interested in meeting (?:them|him|her)"
    r"|this cutie resides at our"
    r"|meetings are by appointment only"
    r"|once we receive your application"
    r"|schedule an appointment"
    r"|no appointment needed"
    r"|please contact us for further information"
    r"|submit an online application",
    re.I,
)

LOCATION_LABELS = {
    "manhattan": "Bideawee Manhattan Adoption Center",
    "westhampton": "Bideawee Westhampton (Long Island)",
    "wantagh": "Bideawee Wantagh (Long Island)",
}


def _clean_ws(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\xa0", " ")).strip()


def description_text(raw_html: str) -> str:
    """Shelterluv Description (HTML) → plain paragraphs."""
    text = raw_html or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h\d)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    paragraphs = [_clean_ws(p) for p in text.split("\n")]
    return "\n".join(p for p in paragraphs if p)


def strip_boilerplate(text: str) -> str:
    """Drop adoption-process sentences; keep everything about the dog."""
    kept_paragraphs = []
    for para in text.split("\n"):
        sentences = re.split(r"(?<=[.!?])\s+", para)
        kept = [s for s in sentences if s.strip() and not BOILERPLATE_SENTENCE_RE.search(s)]
        if kept:
            kept_paragraphs.append(" ".join(kept).strip())
    return "\n".join(kept_paragraphs)


def published_traits(animal: Dict[str, Any]) -> List[str]:
    traits = []
    for name in attribute_names(animal, published_only=True):
        if INTERNAL_ATTRIBUTES_RE.search(name):
            continue
        name = re.sub(r"^BEH\s+", "", name).strip()
        if name and name not in traits:
            traits.append(name)
    return traits


def location_label(animal: Dict[str, Any]) -> str:
    if str(animal.get("InFoster", "")).lower() in ("true", "1", "yes"):
        return "Foster home (NYC / Long Island area)"
    tier1 = ((animal.get("CurrentLocation") or {}).get("Tier1") or "").strip()
    for key, label in LOCATION_LABELS.items():
        if key in tier1.lower():
            return label
    return f"Bideawee {tier1}" if tier1 else ""


def fee_line(animal: Dict[str, Any]) -> str:
    group = animal.get("AdoptionFeeGroup") or {}
    if not group:
        return ""
    name = _clean_ws(group.get("Name") or "")
    try:
        price = float(group.get("Price"))
    except (TypeError, ValueError):
        price = None
    if price is None:
        return f"Adoption fee: {name}" if name else ""
    if price == 0:
        return "Adoption fee: $0 (sponsored adoption)"
    amount = f"${price:,.0f}" if price.is_integer() else f"${price:,.2f}"
    return f"Adoption fee: {amount}" + (f" ({name})" if name else "")


def gender_for(animal: Dict[str, Any]) -> str:
    sex = (animal.get("Sex") or "").strip()
    altered = str(animal.get("Altered", "")).strip().lower() == "yes"
    if sex == "Female":
        return "Spayed Female" if altered else "Female"
    if sex == "Male":
        return "Neutered Male" if altered else "Male"
    return ""


def build_bio(animal: Dict[str, Any]) -> str:
    lines = []
    for label, value in (
        ("Breed", _clean_ws(animal.get("Breed") or "")),
        ("Sex", gender_for(animal)),
        ("Age", format_age(animal.get("Age"))),
        ("Weight", format_weight(animal.get("CurrentWeightPounds"))),
        ("Size", _clean_ws(animal.get("Size") or "")),
        ("Color", _clean_ws(animal.get("Color") or "")),
        ("Location", location_label(animal)),
    ):
        if value:
            lines.append(f"{label}: {value}")
    traits = published_traits(animal)
    if traits:
        lines.append("Traits: " + ", ".join(traits))
    fee = fee_line(animal)
    if fee:
        lines.append(fee)

    narrative = strip_boilerplate(description_text(animal.get("Description") or ""))
    if narrative:
        lines.append("")
        lines.append(narrative)
    return "\n".join(lines).strip()


def narrative_length(animal: Dict[str, Any]) -> int:
    """Length of the dog-specific narrative only (used to pick the bio threshold)."""
    return len(strip_boilerplate(description_text(animal.get("Description") or "")))


def _drop_from_active(aid: str, reason: str) -> None:
    from jobs.lib.db import get_supabase_client

    get_supabase_client().table("active_dogs").delete().eq("animal_id", aid).execute()
    print(json.dumps({"animal_id": aid, "result": f"removed_from_active_dogs_{reason}"}, ensure_ascii=False))


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch one Bideawee dog from Shelterluv and build an animals row."""
    aid = target["animal_id"]
    internal_id = aid[len(SHELTER_ID) + 1:] if aid.startswith(f"{SHELTER_ID}-") else aid
    animal = fetch_animal(internal_id)

    if (animal.get("Type") or "").strip().lower() != "dog":
        raise ValueError("NOT_A_DOG")
    if ADOPTED_ATTRIBUTE in attribute_names(animal):
        _drop_from_active(aid, "adopted")
        raise ValueError("ADOPTED")

    image = animal.get("CoverPhoto") or next(iter(animal.get("Photos") or []), None)

    return {
        "shelter_profile_url": profile_url(animal) if animal.get("Internal-ID") else url,
        "animal_id": aid,
        "shelter_name": SHELTER_NAME,
        "name": clean_name(animal.get("Name") or "") or target.get("name") or "",
        "gender": gender_for(animal) or target.get("gender") or "",
        "age": format_age(animal.get("Age")) or target.get("age") or "",
        "weight": format_weight(animal.get("CurrentWeightPounds")) or target.get("weight") or "",
        "more_info": "",
        "bio": build_bio(animal),
        "shelter_image_url": image,
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def on_http_error(store, target: Dict[str, Any], exc: requests.exceptions.HTTPError) -> None:
    """A 404/410 from Shelterluv means the record is gone — drop it from active_dogs.
    Other errors (auth/5xx) are transient and just logged."""
    aid = target.get("animal_id", "")
    status = exc.response.status_code if exc.response is not None else None
    if aid and status in (404, 410):
        try:
            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
            print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_due_to_http_error",
                              "status_code": status}, ensure_ascii=False))
        except Exception as del_exc:
            print(json.dumps({"animal_id": aid, "error": f"Failed to delete after HTTP {status}: {del_exc}"},
                             ensure_ascii=False), file=sys.stderr)
    print(json.dumps({"url": target.get("url"), "error": str(exc)}, ensure_ascii=False), file=sys.stderr)


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    return run_profiles_scrape(
        shelter_id=SHELTER_ID,
        fetch_record_fn=fetch_record,
        dogs_per_run=DOGS_PER_RUN,
        default_sleep=RUNNER_SLEEP_SECONDS,
        headers=HEADERS,
        extra_fields=["age", "weight"],
        on_http_error=on_http_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
