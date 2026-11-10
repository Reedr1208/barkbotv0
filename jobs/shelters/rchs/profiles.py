"""
RCHS (Rancho Coastal Humane Society) — Profile Scraper

Fetches individual dog profile pages and extracts bio content.
Also downloads and extracts text from Pet Report Card PDFs
for richer biographical data.

This is a WordPress-based site — all data available via HTTP.
Runs via APScheduler using the shared profiles_runner.

Page structure (Elementor theme since Nov 2026):
  • content  — div.elementor-widget-theme-post-content ("Pet Details" block
               with Breed:/Sex:/Age:/Weight: labels, then the bio)
  • photos   — div.sdpets-gallery img (no og:image any more)
  • report   — a.sdpets-pet-button--report-card (PDF)
The older <article> / og:image layout is kept as a fallback.
"""

import io
import logging
import re
import sys
from html import unescape
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from jobs.lib.profiles_runner import run_profiles_scrape


SHELTER_ID = "RCHS"
SHELTER_NAME = "Rancho Coastal Humane Society"
CITY = "San Diego"
STATE = "CA"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def _is_photo_url(url: str) -> bool:
    low = url.lower()
    return (
        "wp-content/uploads" in url
        and not any(bad in low for bad in ("logo", "brand", "seal", "charity-navigator", "_paw_", "bbb"))
    )


def _img_src(img) -> str:
    return img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""


def _find_content(soup: BeautifulSoup):
    """The post-content container (new Elementor theme first, then legacy layouts)."""
    return (
        soup.find(class_="elementor-widget-theme-post-content")
        or soup.find("article")
        or soup.find(class_="entry-content")
    )


def _extract_gallery_image(soup: BeautifulSoup) -> Optional[str]:
    """First photo in the pet gallery (new theme)."""
    gallery = soup.find(class_="sdpets-gallery")
    if not gallery:
        return None
    for img in gallery.find_all("img"):
        src = _img_src(img)
        if src and _is_photo_url(src):
            return src
    return None


def _extract_og_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract og:image URL from meta tags."""
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        url = meta["content"]
        # Skip logos and generic images
        if "logo" not in url.lower() and "brand" not in url.lower():
            return url
    return None


def _extract_article_image(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main dog image from the post content."""
    content = _find_content(soup)
    if not content:
        return None
    
    for img in content.find_all("img"):
        src = _img_src(img)
        # Look for uploads that are actual dog photos (not logos, icons, etc.)
        if src and _is_photo_url(src):
            return src
    return None


def _extract_report_card_url(soup: BeautifulSoup) -> Optional[str]:
    """Find the Pet Report Card PDF link."""
    links = soup.select("a.sdpets-pet-button--report-card[href]") or soup.find_all("a", href=True)
    for link in links:
        href = link["href"]
        if href.lower().endswith(".pdf") and "wp-content/uploads" in href:
            # Skip "coming soon" placeholders
            if "coming-soon" in href.lower():
                continue
            return href
    return None


def _extract_pdf_text(url: str) -> str:
    """Download and extract text from a PDF report card."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logging.warning("pypdf not available; skipping PDF extraction")
        return ""
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        
        reader = PdfReader(io.BytesIO(resp.content))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text.strip())
        
        return "\n\n".join(text_parts)
    except Exception as exc:
        logging.warning(f"Failed to extract PDF text from {url}: {exc}")
        return ""


def _extract_bio_from_article(soup: BeautifulSoup) -> str:
    """Extract the dog bio from the post content."""
    article = _find_content(soup)
    if not article:
        return ""
    
    # Get all text content from the article
    # Remove script/style elements
    for tag in article.find_all(["script", "style", "nav", "noscript", "svg"]):
        tag.decompose()
    
    text = article.get_text(separator="\n", strip=True)

    # Merge "Label:" lines with their value ("Breed:\nTerrier mix" → "Breed: Terrier mix")
    merged: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if merged and merged[-1].endswith(":") and len(merged[-1]) <= 20 and line:
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
    
    # Clean up the text — remove navigation breadcrumbs, social share, etc.
    lines = merged
    cleaned_lines = []
    skip_patterns = [
        r"^Home\s*/", r"^Back To Home", r"^Submit",
        r"^Shelter Hours:", r"^Address:", r"^389 Requeza",
        r"^See Pet Report Card", r"^Click here for detailed",
        r"^Share this", r"^Facebook", r"^Twitter", r"^Pinterest",
        r"^Dogs$", r"^\d{4}$", r"^Pet Details$",
    ]
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        if any(re.match(pat, line, re.I) for pat in skip_patterns):
            continue
        cleaned_lines.append(line)
    
    return "\n".join(cleaned_lines)


def fetch_record(url: str, target: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and parse a single dog profile page."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")

    # Guard against silent layout changes: without this, a theme change saves
    # blank bios / null images over good data (happened Nov 2026). Raising keeps
    # the existing record, counts as a scrape error, and the stale-profile
    # monitor alerts.
    if _find_content(soup) is None:
        raise ValueError(f"RCHS page structure changed: no post-content container at {url}")
    
    # Extract image (new gallery first, then legacy og:image / in-content image)
    image_url = _extract_gallery_image(soup) or _extract_og_image(soup) or _extract_article_image(soup)
    if not image_url and soup.find(class_="sdpets-gallery") is None:
        raise ValueError(f"RCHS page structure changed: no photo gallery found at {url}")
    
    # Extract bio from the article
    bio = _extract_bio_from_article(soup)
    
    # Extract and append report card PDF text
    report_card_url = _extract_report_card_url(soup)
    if report_card_url:
        pdf_text = _extract_pdf_text(report_card_url)
        if pdf_text:
            bio = bio + "\n\n--- Pet Report Card ---\n\n" + pdf_text
    
    # Parse structured info from bio
    gender = None
    age = None
    weight = None
    breed = None
    
    gender_match = re.search(r'\b(Male|Female)\b', bio, re.I)
    if gender_match:
        gender = gender_match.group(1).title()
    
    age_match = re.search(r'(\d+\s*(?:½\s*)?(?:year|month|week)s?)', bio, re.I)
    if age_match:
        age = age_match.group(1).strip()
    
    weight_match = re.search(r'(\d+\s*(?:½\s*)?(?:pound|lb)s?)', bio, re.I)
    if weight_match:
        weight = weight_match.group(1).strip()

    # Extract name from the page title
    title_tag = soup.find("title")
    name = target.get("name", "")
    if title_tag:
        raw_title = title_tag.get_text()
        # Clean "Puffle – Rancho Coastal Humane Society" → "Puffle"
        name = re.sub(r'\s*[–—-]\s*Rancho Coastal.*$', '', raw_title).strip()
    
    return {
        "shelter_profile_url": url,
        "animal_id": target["animal_id"],
        "shelter_name": SHELTER_NAME,
        "name": name,
        "gender": gender or target.get("gender", ""),
        "age": age or target.get("age", ""),
        "weight": weight or "",
        "more_info": "",
        "bio": bio,
        "shelter_image_url": image_url,
        "image_file": None,
        "image_public_url": None,
        "city": CITY,
        "state": STATE,
        "shelter_id": SHELTER_ID,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    return run_profiles_scrape(
        shelter_id=SHELTER_ID,
        fetch_record_fn=fetch_record,
        headers=HEADERS,
        extra_fields=["age"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
