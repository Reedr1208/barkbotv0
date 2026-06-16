"""
PAWSCH (PAWS Chicago) — Profile Scraper

Fetches detailed profiles from pawschicago.org and upserts them
into the animals table via the shared profiles runner.
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from jobs.lib.profiles_runner import run_profiles_scrape

BASE_URL = "https://www.pawschicago.org"
CITY = "Chicago"
STATE = "IL"
SHELTER_ID = "PAWSCH"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


# ═══════════════════════════════════════════════════════════
# PAWSCH-specific HTML parsing helpers
# ═══════════════════════════════════════════════════════════

def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def get_node_text(node: Optional[Tag], sep: str = "\n") -> str:
    if not node:
        return ""
    return clean_text(node.get_text(sep, strip=True))


def text_from_children_as_lines(node: Optional[Tag]) -> str:
    if not node:
        return ""
    section = BeautifulSoup(str(node), "html.parser")
    for bad in section.select("script, style, noscript"):
        bad.decompose()

    lines: List[str] = []
    block_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd"}

    for tag in section.find_all(block_tags):
        text = clean_text(tag.get_text(" ", strip=True))
        if text and text not in lines:
            lines.append(text)

    if not lines:
        text = clean_text(section.get_text("\n", strip=True))
        return text

    return "\n".join(lines)


def make_absolute_url(url: str) -> str:
    if not url:
        return ""
    return urljoin(BASE_URL, url)


def extract_internal_dog_id_from_url(url: str) -> str:
    match = re.search(r"/showdog/(\d+)", url or "")
    return match.group(1) if match else ""


def extract_internal_dog_id(soup: BeautifulSoup, source_url: str = "") -> str:
    canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
    if canonical and canonical.get("href"):
        dog_id = extract_internal_dog_id_from_url(canonical["href"])
        if dog_id:
            return dog_id

    for href_tag in soup.find_all(["a"], href=True):
        dog_id = extract_internal_dog_id_from_url(href_tag["href"])
        if dog_id:
            return dog_id

    return extract_internal_dog_id_from_url(source_url)


def extract_name(soup: BeautifulSoup) -> str:
    candidates: List[str] = []
    breadcrumb_current = soup.select_one(".breadcrumb .current")
    if breadcrumb_current:
        candidates.append(get_node_text(breadcrumb_current, " "))

    know_title = soup.select_one(".know-pet-box .box-title h2")
    if know_title:
        span = know_title.find("span")
        if span:
            candidates.append(get_node_text(span, " "))
        candidates.append(
            clean_text(re.sub(r"^Get to Know\s+", "", know_title.get_text(" ", strip=True), flags=re.I))
        )

    for h2 in soup.find_all("h2"):
        text = get_node_text(h2, " ")
        match = re.match(r"(.+?)['\u2019]s Story$", text)
        if match:
            candidates.append(match.group(1).strip())

    title = soup.find("title")
    if title:
        title_text = get_node_text(title, " ")
        if "|" in title_text:
            candidates.append(title_text.split("|", 1)[0].strip())

    for candidate in candidates:
        candidate = clean_text(candidate)
        if candidate and candidate.lower() not in {"pet profile single view", "pets available"}:
            return candidate

    return ""


def extract_profile_facts(soup: BeautifulSoup) -> Dict[str, str]:
    facts: Dict[str, str] = {}
    for tab in soup.select(".know-pet-box .floating-tabs"):
        label = get_node_text(tab.find(["h4", "h3"]), " ")
        p = tab.find("p")
        value = get_node_text(p, " ") if p else ""
        if label:
            facts[label.lower()] = value

    status_box = soup.select_one(".know-pet-box .box-footer")
    if status_box:
        status_text = get_node_text(status_box, " ")
        status_text = re.sub(r"^Status\s*", "", status_text, flags=re.I).strip()
        facts["status"] = clean_text(status_text)

    return facts


def extract_story_text(soup: BeautifulSoup, name: str) -> str:
    story_node = soup.select_one(".meet-pet .copy-right")
    if story_node:
        lines: List[str] = []
        heading = story_node.find(["h1", "h2", "h3"])
        heading_text = get_node_text(heading, " ")
        if heading_text:
            lines.append(heading_text)

        for p in story_node.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if text:
                lines.append(text)

        if lines:
            return "\n".join(lines)

    for h2 in soup.find_all("h2"):
        h2_text = get_node_text(h2, " ")
        if "story" in h2_text.lower():
            lines = [h2_text]
            for sibling in h2.find_next_siblings():
                if isinstance(sibling, Tag) and sibling.name in {"h1", "h2"}:
                    break
                if isinstance(sibling, Tag):
                    for p in sibling.find_all("p"):
                        p_text = clean_text(p.get_text(" ", strip=True))
                        if p_text:
                            lines.append(p_text)
            if len(lines) > 1:
                return "\n".join(lines)

    return ""


def extract_current_paws_ratings(soup: BeautifulSoup) -> Dict[str, str]:
    ratings: Dict[str, str] = {}
    rating_container = soup.select_one(".meet-pet .rating.top-padding-20") or soup.select_one(".meet-pet .rating")

    if not rating_container:
        return ratings

    for row in rating_container.find_all("div", recursive=False):
        label_node = row.select_one(".icon")
        label = get_node_text(label_node, " ")
        if not label:
            continue

        score = ""
        active = row.select_one(".rating_default span.active")
        if active:
            classes = active.get("class", [])
            for cls in classes:
                match = re.fullmatch(r"r(\d+)", cls)
                if match:
                    score = match.group(1)
                    break

        row_text = get_node_text(row, " ")
        if not score and "unknown" in row_text.lower():
            score = "UNKNOWN"

        ratings[label] = score

    return ratings


def extract_paws_rating_descriptions(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    modal = soup.select_one("#dogs_desciptions")
    descriptions: Dict[str, Dict[str, str]] = {}
    if not modal:
        return descriptions

    for category_block in modal.select(".rating"):
        title_node = category_block.select_one(".rtitle .icon, .dark-brown-bg .icon, .icon")
        category = get_node_text(title_node, " ")
        if not category:
            continue

        descriptions[category] = {}
        for item in category_block.select(".ratings-content-item"):
            score_node = item.find("div")
            desc_node = item.find("p")
            score_text = get_node_text(score_node, " ")
            desc_text = get_node_text(desc_node, " ")
            score_match = re.search(r"(\d+)", score_text)
            if score_match and desc_text:
                descriptions[category][score_match.group(1)] = desc_text

    return descriptions


def format_current_paws_ratings(current_ratings: Dict[str, str], rating_descriptions: Dict[str, Dict[str, str]]) -> str:
    if not current_ratings:
        return ""
    lines = ["PAWS Rating:"]
    for category in ["Children", "Dogs", "Cats", "Home Alone", "Activity", "Environment"]:
        if category not in current_ratings:
            continue
        score = current_ratings.get(category, "")
        description = ""
        if score and score != "UNKNOWN":
            description = rating_descriptions.get(category, {}).get(score, "")
        if description:
            lines.append(f"- {category}: {score}/5 - {description}")
        elif score:
            lines.append(f"- {category}: {score}")
        else:
            lines.append(f"- {category}:")
    return "\n".join(lines)


def format_all_paws_rating_descriptions(rating_descriptions: Dict[str, Dict[str, str]]) -> str:
    if not rating_descriptions:
        return ""
    lines = ["PAWS Rating Scale Definitions:"]
    for category in ["Children", "Dogs", "Cats", "Home Alone", "Activity", "Environment"]:
        values = rating_descriptions.get(category)
        if not values:
            continue
        lines.append(f"{category}:")
        for score in sorted(values, key=lambda s: int(s)):
            lines.append(f"  {score}: {values[score]}")
    return "\n".join(lines)


def extract_more_info(soup: BeautifulSoup, name: str, rating_descriptions: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    sections: List[str] = []
    meet_section = soup.select_one(".pets-story")
    meet_text = text_from_children_as_lines(meet_section)
    if meet_text:
        sections.append(meet_text)
    info_section = soup.select_one(".information")
    info_text = text_from_children_as_lines(info_section)
    if info_text:
        sections.append(info_text)
    steps_heading = soup.select_one("h5.steps")
    if steps_heading:
        steps_parent = steps_heading.parent
        steps_text = text_from_children_as_lines(steps_parent)
        if steps_text and steps_text not in sections:
            sections.append(steps_text)
    scale_text = format_all_paws_rating_descriptions(rating_descriptions or {})
    if scale_text and scale_text not in sections:
        sections.append(scale_text)
    return "\n\n".join(sections)


def extract_images(soup: BeautifulSoup) -> List[str]:
    images = []
    for img in soup.select(".pet-single-carousel img"):
        src = img.get("src") or img.get("datasrc") or img.get("data-src")
        if src:
            abs_src = make_absolute_url(src)
            if abs_src not in images:
                images.append(abs_src)
    return images


def build_bio(name: str, facts: Dict[str, str], story_text: str, current_ratings: Dict[str, str], rating_descriptions: Dict[str, Dict[str, str]]) -> str:
    sections: List[str] = []
    profile_lines = ["Profile Facts:"]
    for label in ["breed", "location", "status"]:
        value = facts.get(label, "")
        if value:
            profile_lines.append(f"- {label.title()}: {value}")
    if len(profile_lines) > 1:
        sections.append("\n".join(profile_lines))
    if story_text:
        sections.append(story_text)
    current_rating_text = format_current_paws_ratings(current_ratings, rating_descriptions)
    if current_rating_text:
        sections.append(current_rating_text)
    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════
# fetch_record — the callback for the shared profiles runner
# ═══════════════════════════════════════════════════════════

def fetch_record(url: str, target: dict) -> Dict[str, Any]:
    """Fetch a PAWSCH profile page and extract the record."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    internal_dog_id = extract_internal_dog_id(soup, url)
    name = extract_name(soup)
    facts = extract_profile_facts(soup)
    story_text = extract_story_text(soup, name)
    current_ratings = extract_current_paws_ratings(soup)
    rating_descriptions = extract_paws_rating_descriptions(soup)
    more_info = extract_more_info(soup, name, rating_descriptions)
    images = extract_images(soup)

    bio = build_bio(name, facts, story_text, current_ratings, rating_descriptions)
    
    shelter_image_url = images[0] if images else None

    return {
        "shelter_profile_url": url,
        "animal_id": f"{SHELTER_ID}-{internal_dog_id}",
        "name": name,
        "shelter_name": "PAWS Chicago",
        "weight": facts.get("weight", ""),
        "age": facts.get("age", ""),
        "more_info": more_info,
        "bio": bio,
        "shelter_image_url": shelter_image_url,
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID
    }


def on_http_error(store, target, exc):
    """Handle HTTP errors — remove adopted dogs from active_dogs."""
    url = target.get("url", "")
    aid = target.get("animal_id", "")
    if not aid:
        native_id = extract_internal_dog_id_from_url(url)
        aid = f"{SHELTER_ID}-{native_id}"
    if exc.response.status_code in (404, 500):
        try:
            store.client.table("active_dogs").delete().eq("animal_id", aid).execute()
            print(json.dumps({"animal_id": aid, "result": "removed_from_active_dogs_due_to_http_error", "status_code": exc.response.status_code}, ensure_ascii=False))
        except Exception as del_exc:
            print(json.dumps({"url": url, "error": f"Failed to delete after HTTP {exc.response.status_code}: {str(del_exc)}"}, ensure_ascii=False), file=sys.stderr)
    print(json.dumps({"url": url, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)


def fallback_url(animal_id: str) -> str:
    internal_id = animal_id.replace(f"{SHELTER_ID}-", "")
    return f"https://www.pawschicago.org/pet-available-for-adoption/showdog/{internal_id}"


def main() -> int:
    return run_profiles_scrape(
        shelter_id=SHELTER_ID,
        fetch_record_fn=fetch_record,
        fallback_url_fn=fallback_url,
        headers=HEADERS,
        on_http_error=on_http_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
