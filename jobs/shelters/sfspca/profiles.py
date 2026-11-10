"""
SFSPCA (San Francisco SPCA) — Profile Scraper

Profile pages (https://www.sfspca.org/sfspca-adoption/{id}/) are server-rendered
WordPress/Elementor posts:

    <body class="... site-{location-slug} ...">     ← adoption site
    ... class="sfspca-adoption-species-dog" ...     ← species marker
    <h1>Name</h1>
    .elementor-widget-theme-post-content            ← narrative <p>s
    .adoptionFacts__div p                           ← Age / Gender / Weight / Breed
        span.adoptionFacts__label--{key} + span.adoptionFacts__value
    .adoptionFacts__tags .elementor-post-info__terms-list-item  ← tags (life stage)

The bio is a short structured header (breed, sex, age, weight, life stage,
location, sponsored fee) followed by the narrative with adoption-process
promos removed (that info lives in shelters.process_details instead).

Non-dogs raise NOT_A_DOG (removed everywhere by the shared runner). Profiles
that 404/410 or redirect off the adoption post type are dropped from
active_dogs.

The site is behind Cloudflare; requests use the browser-like headers from
inventory.py and are spaced out by the runner.

No Playwright needed. Runs via APScheduler using the shared profiles_runner.
"""

import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape
from jobs.shelters.sfspca.inventory import (
    CITY,
    HEADERS,
    PERMALINK_RE,
    SHELTER_ID,
    SHELTER_NAME,
    STATE,
    clean_name,
    format_age,
    format_weight,
    http_get,
)

# ~37 dogs; 15/run refreshes the whole roster every ~3 hours while keeping the
# request rate to Cloudflare low.
DOGS_PER_RUN = 15
RUNNER_SLEEP_SECONDS = 3.0

SPECIES_RE = re.compile(r"sfspca-adoption-species-([a-z0-9-]+)")
SITE_RE = re.compile(r"\bsite-([a-z0-9-]+)")

LOCATION_LABELS = {
    "mission-adoption-center": "SF SPCA Mission Adoption Center (250 Florida St, San Francisco)",
    "leanne-roberts-animal-care-center": "SF SPCA Leanne B. Roberts Animal Care Center (San Francisco)",
    "shelter-annex": "SF SPCA Shelter Annex (San Francisco)",
    "foster-program": "Foster home (SF SPCA foster program)",
}

SPONSORED_RE = re.compile(r"adoption fees? (?:has|have) been (?:generously )?sponsored", re.I)
# Adoption-process promos that repeat across dogs; not about the dog itself.
BOILERPLATE_SENTENCE_RE = re.compile(
    r"adoption fees? (?:has|have) been (?:generously )?sponsored"
    r"|% off your puppy adoption fee"
    r"|puppy parent orientation"
    r"|virtual adoption program"
    r"|adoption application"
    r"|no (?:advance )?appointment",
    re.I,
)


def _clean_ws(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\xa0", " ").replace("\u2028", " ")).strip()


def strip_boilerplate(paragraphs: List[str]) -> str:
    kept_paragraphs = []
    for para in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        kept = [s for s in sentences if s.strip() and not BOILERPLATE_SENTENCE_RE.search(s)]
        if kept:
            kept_paragraphs.append(" ".join(kept).strip())
    return "\n".join(kept_paragraphs)


def _facts(soup: BeautifulSoup) -> Dict[str, str]:
    facts: Dict[str, str] = {}
    for p in soup.select(".adoptionFacts__div p"):
        label = p.find(class_=re.compile(r"adoptionFacts__label--"))
        value = p.select_one(".adoptionFacts__value")
        if not label or not value:
            continue
        key = next(c for c in label["class"] if c.startswith("adoptionFacts__label--")).split("--", 1)[1]
        screen_only = value.select_one(".elementor-screen-only")
        text = screen_only.get_text(" ", strip=True) if screen_only else value.get_text(" ", strip=True)
        facts[key.lower()] = _clean_ws(text)
    return facts


def _image(soup: BeautifulSoup) -> Optional[str]:
    slide = soup.select_one("img.swiper-slide-image")
    if slide and slide.get("src"):
        return slide["src"]
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content") and "logo" not in meta["content"].lower():
        return meta["content"]
    return None


def parse_profile(page_html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    body = soup.find("body")
    body_classes = " ".join(body.get("class", [])) if body else ""
    species = SPECIES_RE.findall(page_html)
    site = SITE_RE.search(body_classes)

    # The post-title widget holds the name. Don't take the first <h1>: the site
    # shows announcement banners (e.g. holiday hours) as <h1>s above it.
    h1 = soup.select_one(".elementor-widget-theme-post-title h1, .elementor-widget-theme-post-title .elementor-heading-title")
    if h1 is None:
        og_title = soup.find("meta", property="og:title")
        title_text = re.sub(r"\s*[-|–]\s*San Francisco SPCA\s*$", "", og_title.get("content", "")) if og_title else ""
    else:
        title_text = h1.get_text(" ", strip=True)
    content = soup.select_one(".elementor-widget-theme-post-content .elementor-widget-container")
    paragraphs = []
    if content is not None:
        for br in content.find_all("br"):
            br.replace_with("\n")
        for block in content.find_all(["p", "li", "h2", "h3", "h4"]) or [content]:
            for line in block.get_text("").split("\n"):
                line = _clean_ws(line)
                if line:
                    paragraphs.append(line)

    facts = _facts(soup)
    tags = [_clean_ws(t.get_text(" ", strip=True))
            for t in soup.select(".adoptionFacts__tags .elementor-post-info__terms-list-item")]
    life_stage = next((t for t in tags if t.lower() in
                       ("puppy", "juvenile", "young adult", "adult", "senior")), "")

    return {
        "species": species,
        "site": site.group(1) if site else "",
        "name": clean_name(title_text),
        "facts": facts,
        "life_stage": life_stage,
        "sponsored": any(SPONSORED_RE.search(p) for p in paragraphs),
        "narrative": strip_boilerplate(paragraphs),
        "image_url": _image(soup),
        "has_content": content is not None or bool(facts),
    }


def build_bio(parsed: Dict[str, Any]) -> str:
    facts = parsed["facts"]
    lines = []
    for label, value in (
        ("Breed", facts.get("breed", "")),
        ("Sex", facts.get("gender", "")),
        ("Age", format_age(facts.get("age", ""))),
        ("Weight", format_weight(facts.get("weight", ""))),
        ("Life stage", parsed["life_stage"]),
        ("Location", LOCATION_LABELS.get(parsed["site"], parsed["site"].replace("-", " ").title())),
    ):
        if value:
            lines.append(f"{label}: {value}")
    if parsed["sponsored"]:
        lines.append("Adoption fee: sponsored (waived)")
    if parsed["narrative"]:
        lines.append("")
        lines.append(parsed["narrative"])
    return "\n".join(lines).strip()


def _drop_from_active(aid: str, reason: str) -> None:
    from jobs.lib.db import get_supabase_client

    get_supabase_client().table("active_dogs").delete().eq("animal_id", aid).execute()
    print(json.dumps({"animal_id": aid, "result": f"removed_from_active_dogs_{reason}"}, ensure_ascii=False))


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single SF SPCA profile page."""
    aid = target["animal_id"]
    resp = http_get(url)
    resp.raise_for_status()

    # Adopted/unpublished posts may redirect to a listing page instead of 404ing.
    if not PERMALINK_RE.match(resp.url):
        _drop_from_active(aid, "redirected")
        raise ValueError(f"NO_LONGER_LISTED (redirected to {resp.url})")

    parsed = parse_profile(resp.text)
    if parsed["species"] and "dog" not in parsed["species"]:
        raise ValueError("NOT_A_DOG")
    if not parsed["species"] or not parsed["has_content"]:
        raise ValueError("SF SPCA profile markers not found — page structure may have changed")

    facts = parsed["facts"]
    gender = facts.get("gender", "")
    return {
        "shelter_profile_url": url,
        "animal_id": aid,
        "shelter_name": SHELTER_NAME,
        "name": parsed["name"] or target.get("name") or "",
        "gender": gender if gender in ("Male", "Female") else (target.get("gender") or ""),
        "age": format_age(facts.get("age", "")) or target.get("age") or "",
        "weight": format_weight(facts.get("weight", "")) or target.get("weight") or "",
        "more_info": "",
        "bio": build_bio(parsed),
        "shelter_image_url": parsed["image_url"],
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def on_http_error(store, target: Dict[str, Any], exc: requests.exceptions.HTTPError) -> None:
    """A 404/410 means the post was unpublished (adopted) — drop it from active_dogs.
    Other errors (e.g. Cloudflare 403/5xx) are transient and just logged."""
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
