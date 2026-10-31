"""
PAWSCO (PawsCo, Denver CO) — Profile Scraper

Profile pages (https://pawsco.org/animals/meet-{slug}) are static WordPress
"portfolio" posts. The useful content lives in #portfolio-single-content as a
series of <p> blocks with bold labels, e.g.

    Name: Josie / Breed: Beagle Mix / Sex: Spayed Female / Age: 12 years /
    Weight: 30 lbs / Animal Number: 4717
    <tagline, e.g. "Super Sweet, Calm, Quiet, Lovable">
    Good with dogs? … / Good with cats? … / Good with kids? …
    Energy level: … / Medical needs: … / Behavioral needs: …
    Animal Characteristics: <narrative>
    Please learn more about the adoption process … My adoption fee is $300 …

Labels are hand-typed per post (some posts omit Breed / Animal Number, or split
"Animal Number" across tags), so parsing is label-tolerant and the bio keeps
every labelled block verbatim. The trailing adoption boilerplate is dropped
except for the adoption fee.

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
from jobs.shelters.pawsco.inventory import (
    CITY,
    HEADERS,
    SHELTER_ID,
    SHELTER_NAME,
    STATE,
    polite_request,
)

# Each dog costs ~3 pawsco.org requests (page + image HEAD + image GET), and
# Cloudflare rate-limits bursts. 10 dogs/hour still refreshes the whole
# (~15-dog) roster every ~2 hours.
DOGS_PER_RUN = 10
RUNNER_SLEEP_SECONDS = 5.0

BOILERPLATE_RE = re.compile(r"learn more about the adoption process|contact my friends at pawsco", re.I)
FEE_RE = re.compile(r"adoption fee is\s*(\$\s?[\d,]+(?:\.\d{2})?)", re.I)
LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]{1,30}?)\s*:\s*(.*)$")


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\xa0", " ")).strip()


def _block_lines(block) -> List[str]:
    """Text of a <p>/<li> block, splitting on <br> and fixing 'Label : value' spacing."""
    for br in block.find_all("br"):
        br.replace_with("\n")
    text = block.get_text("")
    lines = []
    for line in text.split("\n"):
        line = _clean(line)
        if not line:
            continue
        line = re.sub(r"\s+:", ":", line)       # "Name : X" → "Name: X"
        line = re.sub(r":(?=\S)", ": ", line, count=1) if LABEL_RE.match(line) else line
        lines.append(line)
    return lines


def _extract_image(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content") and "/wp-content/uploads/" in meta["content"]:
        return meta["content"]
    media = soup.select_one("#portfolio-single-media img")
    if media:
        return media.get("data-src") or media.get("src")
    return None


def parse_profile(html: str) -> Dict[str, Any]:
    """Parse a PawsCo profile page into structured fields + bio text."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#portfolio-single-content") or soup.select_one(".single-content")
    if content is None:
        raise ValueError("PawsCo profile content block not found — page structure may have changed")

    fields: Dict[str, str] = {}
    bio_lines: List[str] = []
    fee = ""

    for block in content.find_all(["p", "li", "h2", "h3", "h4"]):
        lines = _block_lines(block)
        if not lines:
            continue
        joined = " ".join(lines)
        if BOILERPLATE_RE.search(joined):
            m = FEE_RE.search(joined)
            if m:
                fee = m.group(1).replace(" ", "")
            continue
        for line in lines:
            m = LABEL_RE.match(line)
            if m:
                fields.setdefault(m.group(1).strip().lower(), m.group(2).strip())
        bio_lines.extend(lines)

    if fee:
        bio_lines.append(f"Adoption fee: {fee}")

    h1 = soup.select_one("h1")
    title_name = _clean(re.sub(r"^meet\s+|!+$", "", h1.get_text(" ", strip=True), flags=re.I)) if h1 else ""

    sex = fields.get("sex", "")
    gender = ""
    if re.search(r"\bfemale\b", sex, re.I):
        gender = sex if re.search(r"spayed|unaltered|intact", sex, re.I) else "Female"
    elif re.search(r"\bmale\b", sex, re.I):
        gender = sex if re.search(r"neutered|unaltered|intact", sex, re.I) else "Male"

    return {
        "name": fields.get("name") or title_name,
        "title_name": title_name,
        "gender": gender,
        "age": fields.get("age", ""),
        "weight": fields.get("weight", ""),
        "breed": fields.get("breed", ""),
        "animal_number": fields.get("animal number", ""),
        "bio": "\n".join(bio_lines),
        "image_url": _extract_image(soup),
    }


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single PawsCo profile page."""
    resp = polite_request("GET", url)
    resp.raise_for_status()
    parsed = parse_profile(resp.text)

    # Inventory names come from the card's first line ("Juniper"); profile "Name:"
    # lines can be long nicknames ("Juniper Zoomie Queen of …"), which stay in the bio.
    name = target.get("name") or parsed["title_name"] or parsed["name"]

    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name,
        "gender": parsed["gender"] or target.get("gender") or "",
        "age": parsed["age"] or target.get("age") or "",
        "weight": parsed["weight"] or target.get("weight") or "",
        "more_info": "",
        "bio": parsed["bio"],
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
