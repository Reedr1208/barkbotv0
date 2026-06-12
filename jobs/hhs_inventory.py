"""
Scrape Houston Humane Society dog adoptables from their Shelterluv-powered page.

Install once:
    pip install playwright
    python -m playwright install chromium

Run:
    python hhs_inventory.py

All runtime variables are defined below. No command-line arguments are required.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from supabase import create_client


# =============================================================================
# CONFIG - edit these values directly in the script
# =============================================================================
START_URL = "https://www.houstonhumane.org/adopt-a-pet/dog-adoptables"
DEBUG_ROOT = "debug"

# For testing, stop after X dogs. Set to None to scrape everything found.
MAX_DOGS: Optional[int] = None

HEADLESS = True
BROWSER_SLOW_MO_MS = 0
NAVIGATION_TIMEOUT_MS = 60_000
RENDER_WAIT_MS = 8_000
BETWEEN_PAGE_WAIT_MS = 2_000
MAX_PAGES_TO_TRY = 100
MAX_SCROLL_ROUNDS_PER_PAGE = 8

# Animal IDs will be HHS-{numeric_internal_id}. Example: HHS-2078.
ANIMAL_ID_PREFIX = "HHS"

# Shelterluv profile URLs commonly look like:
# https://new.shelterluv.com/embed/animal/UPRW-A-62922
SHELTERLUV_PROFILE_BASE = "https://new.shelterluv.com/embed/animal/"

# =============================================================================
# END CONFIG
# =============================================================================


DOG_ID_PATTERNS = [
    re.compile(r"/embed/animal/([^/?#\"'<>\s]+)", re.I),
    re.compile(r"\b([A-Z0-9]{2,12}-A-\d{2,})\b", re.I),
    # Fallback for Shelterluv profiles that use a numeric animal ID.
    re.compile(r"\b(\d{5,})\b"),
]

SKIP_IMAGE_PATTERNS = re.compile(
    r"(logo|favicon|badge|charity|guidestar|bbb|amazon|facebook|instagram|youtube|tiktok|pixel|tracking)",
    re.I,
)


def get_supabase_client():
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        # Fallback to standard env vars
        try:
            supabase_url = os.environ["SUPABASE_URL"]
            supabase_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
            return create_client(supabase_url, supabase_key)
        except KeyError:
            raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_debug_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(DEBUG_ROOT) / f"HHS_inventory_{ts}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(debug_dir: Path) -> None:
    log_path = debug_dir / "scraper.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.info("Debug folder: %s", debug_dir.resolve())


def safe_filename(value: str, max_len: int = 120) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return value[:max_len] or "file"


def abs_url(base_url: str, maybe_url: str) -> str:
    if not maybe_url:
        return ""
    maybe_url = maybe_url.strip()
    if maybe_url.startswith("//"):
        return "https:" + maybe_url
    return urljoin(base_url, maybe_url)


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    value = re.sub(r"'s preview photo.*$", "", value, flags=re.I).strip()
    value = re.sub(r"\bpreview photo\b.*$", "", value, flags=re.I).strip()
    value = re.sub(r"\bavailable for adoption\b.*$", "", value, flags=re.I).strip()
    # Shelterluv text often starts with the name followed by demographic text.
    value = re.split(r"\b(?:Male|Female|Unknown),\b", value, maxsplit=1, flags=re.I)[0].strip()
    return value


def extract_gender_age(tile_text: str) -> tuple[str, str]:
    gender = ""
    age = ""
    # "Male, Adult", "Female, Young", etc.
    match = re.search(r"\b(Male|Female|Unknown),\s*(Baby|Young|Adult|Senior)\b", tile_text, re.I)
    if match:
        gender = match.group(1).title()
        age = match.group(2).title()
    else:
        # Fallback if comma is missing or order is different
        gender_match = re.search(r"\b(Male|Female)\b", tile_text, re.I)
        if gender_match:
            gender = gender_match.group(1).title()
        age_match = re.search(r"\b(Baby|Young|Adult|Senior)\b", tile_text, re.I)
        if age_match:
            age = age_match.group(1).title()
            
    return gender, age


def extract_internal_dog_id(*values: str) -> str:
    joined = "\n".join(v for v in values if v)
    for pattern in DOG_ID_PATTERNS:
        match = pattern.search(joined)
        if match:
            return match.group(1).strip()
    return ""


def build_animal_id(internal_dog_id: str) -> str:
    raw_id = (internal_dog_id or "").strip().strip("/")
    if not raw_id:
        return ""

    match = re.search(r"(\d+)$", raw_id)
    numeric_id = match.group(1) if match else raw_id

    prefix = ANIMAL_ID_PREFIX.strip().rstrip("-")
    return f"{prefix}-{numeric_id}"


def build_profile_url(internal_dog_id: str, existing_url: str = "") -> str:
    existing_url = (existing_url or "").strip()
    if existing_url and not existing_url.lower().startswith("javascript:"):
        return existing_url
    if internal_dog_id:
        return SHELTERLUV_PROFILE_BASE + internal_dog_id
    return ""


def is_probably_dog_record(row: Dict[str, Any]) -> bool:
    name = clean_name(row.get("name", ""))
    image = row.get("public_image_url", "") or ""
    profile = row.get("shelter_profile_url", "") or ""
    internal_id = row.get("internal_dog_id", "") or ""
    tile_text = row.get("tile_text", "") or ""
    joined = " ".join([name, image, profile, internal_id, tile_text])

    if not name:
        return False
    if len(name) > 80:
        return False
    if not image:
        return False
    if image.startswith("data:"):
        return False
    if SKIP_IMAGE_PATTERNS.search(joined):
        return False

    if internal_id or "/embed/animal/" in profile.lower() or "shelterluv" in joined.lower():
        return True

    return False


def normalize_record(raw: Dict[str, Any], page_url: str) -> Optional[Dict[str, str]]:
    name = clean_name(raw.get("name", ""))
    public_image_url = abs_url(page_url, raw.get("public_image_url", ""))
    shelter_profile_url = abs_url(page_url, raw.get("shelter_profile_url", ""))
    tile_text = raw.get("tile_text", "")

    candidate_text = "\n".join(
        str(v)
        for v in [
            raw.get("internal_dog_id", ""),
            shelter_profile_url,
            raw.get("tile_html", ""),
            tile_text,
            "\n".join(raw.get("id_candidates", []) or []),
        ]
        if v
    )
    internal_dog_id = extract_internal_dog_id(candidate_text)
    shelter_profile_url = build_profile_url(internal_dog_id, shelter_profile_url)
    animal_id = build_animal_id(internal_dog_id)

    gender, age = extract_gender_age(tile_text)

    row = {
        "name": name,
        "animal_id": animal_id,
        "gender": gender,
        "age": age,
        "weight": "", # Often not available on tile
        "city": "Houston",
        "state": "TX",
        "shelter_name": "Houston Humane Society",
        "shelter_id": "HHS",
        "scraped_at": now_iso()
    }

    debug_row = dict(row)
    debug_row["tile_text"] = tile_text
    if not is_probably_dog_record({**debug_row, "tile_html": raw.get("tile_html", "")}):
        return None

    return row


def dedupe_records(records: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for row in records:
        key = row.get("animal_id") or row.get("shelter_profile_url") or row.get("public_image_url")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def save_debug_json(debug_dir: Path, filename: str, data: Any) -> None:
    path = debug_dir / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_embed_config_from_html(html: str) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    container = re.search(r'id=["\'](shelterluv_wrap_\d+)["\']', html, re.I)
    if container:
        config["container_id"] = container.group(1)
    gid = re.search(r"\bGID\s*=\s*(\d+)", html)
    if gid:
        config["GID"] = int(gid.group(1))
    source = re.search(r"\bsourceDomain\s*=\s*[\"']([^\"']+)[\"']", html)
    if source:
        config["sourceDomain"] = source.group(1)
    filters = re.search(r"\bfilters\s*=\s*(\{.*?\}|\[.*?\])\s*;", html, re.S)
    if filters:
        config["filters_raw"] = filters.group(1)
    return config


EXTRACT_JS = r"""
() => {
  function absUrl(u) {
    if (!u) return '';
    try { return new URL(u, document.location.href).href; } catch (e) { return u; }
  }

  function cleanName(s) {
    s = (s || '').replace(/\s+/g, ' ').trim();
    s = s.replace(/'s preview photo.*$/i, '').trim();
    s = s.replace(/\bpreview photo\b.*$/i, '').trim();
    s = s.replace(/\bavailable for adoption\b.*$/i, '').trim();
    s = s.split(/\b(?:Male|Female|Unknown),\b/i)[0].trim();
    return s;
  }

  function attrCandidates(el) {
    const out = [];
    if (!el || !el.getAttributeNames) return out;
    for (const attr of el.getAttributeNames()) {
      const val = el.getAttribute(attr) || '';
      if (/embed\/animal\//i.test(val) || /\b[A-Z0-9]{2,12}-A-\d{2,}\b/i.test(val) || /\b\d{5,}\b/.test(val)) {
        out.push(`${attr}=${val}`);
      }
    }
    return out;
  }

  function findTile(el) {
    let cur = el;
    for (let depth = 0; depth < 10 && cur; depth++, cur = cur.parentElement) {
      const txt = (cur.innerText || '').trim();
      const imgCount = cur.querySelectorAll ? cur.querySelectorAll('img').length : 0;
      const anchorCount = cur.querySelectorAll ? cur.querySelectorAll('a[href]').length : 0;
      const looksSmallEnough = txt.length > 0 && txt.length < 500 && imgCount >= 1 && imgCount <= 4;
      const hasAnimalLink = cur.querySelector && cur.querySelector('a[href*="/embed/animal/"]');
      const hasPreviewAlt = cur.querySelector && cur.querySelector('img[alt*="preview photo" i]');
      if (hasAnimalLink || hasPreviewAlt || looksSmallEnough || (txt && anchorCount === 1 && imgCount >= 1)) {
        return cur;
      }
    }
    return el.closest('a[href]') || el.parentElement || el;
  }

  function bestName(img, tile, anchor) {
    const alt = cleanName(img.getAttribute('alt') || img.getAttribute('title') || '');
    if (alt) return alt;

    const aria = cleanName((anchor && (anchor.getAttribute('aria-label') || anchor.getAttribute('title'))) || '');
    if (aria) return aria;

    if (tile) {
      const lines = (tile.innerText || '')
        .split(/\n+/)
        .map(x => cleanName(x))
        .filter(Boolean);
      if (lines.length) return lines[0];
    }
    return '';
  }

  const roots = Array.from(document.querySelectorAll('[id^="shelterluv_wrap"]'));
  const root = roots.find(r => (r.innerText || '').trim() || r.querySelector('img')) || document.body;

  let scrapeIndex = 0;
  const results = [];

  for (const img of Array.from(root.querySelectorAll('img'))) {
    const tile = findTile(img);
    if (tile && tile.setAttribute) {
      tile.setAttribute('data-hsa-scrape-index', String(scrapeIndex++));
    }

    const anchor = img.closest('a[href]') || (tile && tile.querySelector ? tile.querySelector('a[href]') : null);
    const href = anchor ? absUrl(anchor.getAttribute('href') || '') : '';
    const image = absUrl(
      img.currentSrc ||
      img.getAttribute('src') ||
      img.getAttribute('data-src') ||
      img.getAttribute('data-lazy-src') ||
      ''
    );

    const pieces = [img, anchor, tile].filter(Boolean);
    const idCandidates = [];
    for (const p of pieces) idCandidates.push(...attrCandidates(p));

    const tileText = tile ? (tile.innerText || '').replace(/\s+$/g, '').trim() : '';
    const tileHtml = tile ? (tile.outerHTML || '').slice(0, 5000) : '';

    results.push({
      name: bestName(img, tile, anchor),
      public_image_url: image,
      shelter_profile_url: href,
      tile_text: tileText,
      tile_html: tileHtml,
      id_candidates: idCandidates,
      frame_url: document.location.href,
      scrape_index: tile ? tile.getAttribute('data-hsa-scrape-index') : ''
    });
  }

  for (const el of Array.from(root.querySelectorAll('[style*="background"]'))) {
    const style = el.getAttribute('style') || '';
    const m = style.match(/url\(["']?([^"')]+)["']?\)/i);
    if (!m) continue;
    const tile = findTile(el);
    const anchor = el.closest('a[href]') || (tile && tile.querySelector ? tile.querySelector('a[href]') : null);
    if (tile && tile.setAttribute && !tile.getAttribute('data-hsa-scrape-index')) {
      tile.setAttribute('data-hsa-scrape-index', String(scrapeIndex++));
    }
    const idCandidates = [];
    for (const p of [el, anchor, tile].filter(Boolean)) idCandidates.push(...attrCandidates(p));
    const tileText = tile ? (tile.innerText || '').replace(/\s+$/g, '').trim() : '';
    results.push({
      name: cleanName(tileText.split(/\n+/)[0] || ''),
      public_image_url: absUrl(m[1]),
      shelter_profile_url: anchor ? absUrl(anchor.getAttribute('href') || '') : '',
      tile_text: tileText,
      tile_html: tile ? (tile.outerHTML || '').slice(0, 5000) : '',
      id_candidates: idCandidates,
      frame_url: document.location.href,
      scrape_index: tile ? tile.getAttribute('data-hsa-scrape-index') : ''
    });
  }

  return results;
}
"""


FIND_NEXT_JS = r"""
() => {
  const roots = Array.from(document.querySelectorAll('[id^="shelterluv_wrap"]'));
  const root = roots.find(r => (r.innerText || '').trim() || r.querySelector('img')) || document.body;
  const candidates = Array.from(root.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]'));

  function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }

  function disabled(el) {
    return el.disabled ||
      el.getAttribute('aria-disabled') === 'true' ||
      /\bdisabled\b/i.test(el.className || '') ||
      /\bdisabled\b/i.test(el.getAttribute('class') || '');
  }

  const patterns = [/^next$/i, /next/i, /load more/i, /show more/i, /^›$/, /^>$/, /^»$/];
  for (const el of candidates) {
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (!visible(el) || disabled(el)) continue;
    if (patterns.some(p => p.test(text))) {
      el.setAttribute('data-hsa-next-candidate', '1');
      return true;
    }
  }
  return false;
}
"""


CLICK_NEXT_JS = r"""
() => {
  const el = document.querySelector('[data-hsa-next-candidate="1"]');
  if (el) {
    el.scrollIntoView({block: 'center'});
    el.click();
    return true;
  }
  return false;
}
"""


def extract_from_all_frames(page, debug_dir: Path, page_num: int) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    raw_rows: List[Dict[str, Any]] = []
    for frame_index, frame in enumerate(page.frames):
        try:
            frame_rows = frame.evaluate(EXTRACT_JS)
            if frame_rows:
                logging.info("Frame %s (%s) yielded %s raw image/tile rows", frame_index, frame.url, len(frame_rows))
                for row in frame_rows:
                    row["_frame_index"] = frame_index
                    row["_frame_url"] = frame.url
                raw_rows.extend(frame_rows)
        except Exception as exc:
            logging.debug("Could not evaluate frame %s (%s): %s", frame_index, frame.url, exc)

    save_debug_json(debug_dir, f"page_{page_num:03d}_raw_tiles.json", raw_rows)

    normalized: List[Dict[str, str]] = []
    for raw in raw_rows:
        page_url = raw.get("frame_url") or page.url
        row = normalize_record(raw, page_url)
        if row:
            normalized.append(row)

    normalized = dedupe_records(normalized)
    save_debug_json(debug_dir, f"page_{page_num:03d}_normalized_records.json", normalized)
    return normalized, raw_rows


def maybe_click_next(page) -> bool:
    for frame in page.frames:
        try:
            has_next = frame.evaluate(FIND_NEXT_JS)
            if has_next:
                logging.info("Clicking next/load-more control in frame: %s", frame.url)
                clicked = frame.evaluate(CLICK_NEXT_JS)
                if clicked:
                    page.wait_for_timeout(BETWEEN_PAGE_WAIT_MS)
                    return True
        except Exception as exc:
            logging.debug("Next detection failed in frame %s: %s", frame.url, exc)
    return False


def scroll_for_more(page, seen_count: int) -> bool:
    for i in range(MAX_SCROLL_ROUNDS_PER_PAGE):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1_000)
        try:
            img_count = page.evaluate("document.querySelectorAll('img').length")
        except Exception:
            img_count = 0
        if img_count > seen_count:
            return True
    return False


def save_to_supabase(dogs: list[dict]):
    if not dogs:
        logging.info("No dogs to save.")
        return

    if len(dogs) < 10:
        raise RuntimeError(f"Safety check failed: Only {len(dogs)} dogs scraped. Aborting to prevent accidental data loss.")

    client = get_supabase_client()

    logging.info("Clearing existing active_dogs table data for HHS...")
    client.table("active_dogs").delete().eq("shelter_id", "HHS").execute()

    logging.info(f"Inserting {len(dogs)} dogs into active_dogs...")
    
    # Supabase insert bulk data safely
    client.table("active_dogs").insert(dogs).execute()
    logging.info("Insert complete.")


def main() -> None:
    debug_dir = make_debug_dir()
    setup_logging(debug_dir)

    all_records: List[Dict[str, str]] = []
    seen_keys = set()
    network_events: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=BROWSER_SLOW_MO_MS)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(NAVIGATION_TIMEOUT_MS)

        def on_response(response):
            url = response.url
            lower = url.lower()
            if "shelterluv" not in lower and "animal" not in lower and "available" not in lower:
                return
            item = {
                "url": url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
            network_events.append(item)
            try:
                content_type = item["content_type"].lower()
                if "json" in content_type or "text" in content_type or "html" in content_type or "javascript" in content_type:
                    text = response.text()
                    item["body_preview"] = text[:1000]
                    fname = safe_filename(f"response_{len(network_events):03d}_{urlparse(url).netloc}_{urlparse(url).path}")
                    (debug_dir / f"{fname}.txt").write_text(text[:250_000], encoding="utf-8", errors="replace")
            except Exception as exc:
                item["read_error"] = str(exc)

        page.on("response", on_response)

        logging.info("Opening %s", START_URL)
        page.goto(START_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

        try:
            page.wait_for_load_state("networkidle", timeout=RENDER_WAIT_MS)
        except PlaywrightTimeoutError:
            logging.info("networkidle wait timed out; continuing after fixed render wait")
        page.wait_for_timeout(RENDER_WAIT_MS)

        initial_html = page.content()
        (debug_dir / "initial_rendered_page.html").write_text(initial_html, encoding="utf-8", errors="replace")
        save_debug_json(debug_dir, "shelterluv_embed_config.json", parse_embed_config_from_html(initial_html))
        page.screenshot(path=str(debug_dir / "initial_rendered_page.png"), full_page=True)

        page_num = 1
        while page_num <= MAX_PAGES_TO_TRY:
            logging.info("Extracting page/iteration %s", page_num)
            try:
                (debug_dir / f"page_{page_num:03d}.html").write_text(page.content(), encoding="utf-8", errors="replace")
                page.screenshot(path=str(debug_dir / f"page_{page_num:03d}.png"), full_page=True)
            except Exception as exc:
                logging.warning("Could not save page debug artifacts: %s", exc)

            page_records, raw_rows = extract_from_all_frames(page, debug_dir, page_num)
            before = len(all_records)
            for row in page_records:
                key = row.get("animal_id") or row.get("shelter_profile_url") or row.get("public_image_url")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                
                # Exclude debug keys before saving to DB
                db_row = dict(row)
                db_row.pop("internal_dog_id", None)
                
                all_records.append(db_row)
                logging.info("Added dog: %s | %s", row.get("name"), row.get("animal_id"))
                if MAX_DOGS is not None and len(all_records) >= MAX_DOGS:
                    break

            if MAX_DOGS is not None and len(all_records) >= MAX_DOGS:
                logging.info("Reached MAX_DOGS=%s; stopping run.", MAX_DOGS)
                break

            added_this_round = len(all_records) - before
            clicked_next = maybe_click_next(page)
            if clicked_next:
                page_num += 1
                continue

            raw_img_count = len(raw_rows)
            if scroll_for_more(page, raw_img_count):
                page.wait_for_timeout(BETWEEN_PAGE_WAIT_MS)
                page_num += 1
                continue

            if added_this_round == 0:
                logging.info("No new records and no pagination found; stopping.")
                break

            logging.info("No next/load-more control found after adding records; stopping.")
            break

        save_debug_json(debug_dir, "network_events.json", network_events)
        
        final_records = [r for r in all_records if r.get("animal_id")]
        
        logging.info("Done scraping. Final row count: %s", len(final_records))
        browser.close()
        
        save_to_supabase(final_records)


if __name__ == "__main__":
    main()
