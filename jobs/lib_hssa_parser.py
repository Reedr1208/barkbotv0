#!/usr/bin/env python3
"""
Scrape Humane Society of Southern Arizona dog profile data from Adopt-a-Pet pet pages.

Examples:
  python scrape_hssa_adoptapet.py 47648753
  python scrape_hssa_adoptapet.py 47648753 47612345 --out hssa_dogs.csv
  python scrape_hssa_adoptapet.py --html-file humane_society_yume.html --no-download --json
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import mimetypes
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.adoptapet.com/pet/{pet_id}"
LOCATED_AT_DEFAULT = "Humane Society of Southern Arizona"

FIELDNAMES = [
    "animal_id",
    "shelter_profile_url",
    "shelter_name",
    "weight",
    "age",
    "more_info",
    "bio",
    "shelter_image_url",
    "city",
    "state",
    "shelter_id"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def clean_text(value: Optional[str]) -> Optional[str]:
    """Convert small HTML fragments / escaped text into a clean single-line string."""
    if value is None:
        return None

    value = html_lib.unescape(str(value))
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def title_age(value: Optional[str]) -> Optional[str]:
    value = clean_text(value)
    return value.title() if value else None


def normalize_weight(value: Optional[str]) -> Optional[str]:
    """Convert values like '84 lbs (current)' to '84Lbs'."""
    value = clean_text(value)
    if not value:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*lbs?\b", value, flags=re.I)
    if match:
        return f"{match.group(1)}Lbs"

    return value


def decode_next_f_payloads(html_text: str) -> str:
    """
    Adopt-a-Pet/Next.js embeds the useful pet object inside self.__next_f.push(...)
    script chunks. This decodes those JS string chunks and concatenates them.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    decoded_chunks: list[str] = []

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text() or ""
        if "self.__next_f.push" not in script_text:
            continue

        # Common pattern: self.__next_f.push([1,"..."])
        match = re.search(r"self\.__next_f\.push\(\[1,\"(.*)\"\]\)$", script_text, flags=re.S)
        if not match:
            continue

        raw_js_string = match.group(1)
        try:
            decoded_chunks.append(json.loads(f'"{raw_js_string}"'))
        except json.JSONDecodeError:
            # Best-effort fallback for unusual escaping.
            decoded_chunks.append(bytes(raw_js_string, "utf-8").decode("unicode_escape", errors="ignore"))

    return "\n".join(decoded_chunks)


def extract_balanced_json_object(text: str, start_idx: int) -> str:
    """Return JSON object text starting at start_idx, respecting strings and escapes."""
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        raise ValueError("start_idx does not point to a JSON object")

    depth = 0
    in_string = False
    escape = False

    for i in range(start_idx, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]

    raise ValueError("Could not find end of JSON object")


def extract_pet_details(html_text: str) -> dict[str, Any]:
    """Extract the embedded PetDetails JSON object from the page HTML."""
    decoded = decode_next_f_payloads(html_text)

    # Search decoded Next.js payload first, then raw HTML as a last resort.
    for haystack in (decoded, html_text):
        marker = '"pet":{"__typename":"PetDetails"'
        idx = haystack.find(marker)
        if idx == -1:
            continue

        pet_key_idx = haystack.rfind('"pet":', 0, idx + len(marker))
        start = haystack.find("{", pet_key_idx + len('"pet":'))
        if start == -1:
            continue

        pet_json = extract_balanced_json_object(haystack, start)
        return json.loads(pet_json)

    raise ValueError("Could not find embedded PetDetails object in page HTML.")


def parse_srcset(srcset: str) -> list[tuple[int, str]]:
    """
    Return [(width_score, url), ...] from an HTML srcset string.

    Note: Adopt-a-Pet image URLs contain commas in the Cloudinary transform path
    such as /c_fit,h_523,dpr_2/. Because of that, a naive srcset.split(",")
    will corrupt the URL. This regex uses the width/density descriptor as the
    candidate boundary instead.
    """
    candidates: list[tuple[int, str]] = []

    pattern = re.compile(r"(\S+)\s+(\d+w|\d+(?:\.\d+)?x)(?:\s*,\s*|$)")
    for match in pattern.finditer(srcset.strip()):
        url = match.group(1)
        descriptor = match.group(2).lower()

        if descriptor.endswith("w"):
            score = int(descriptor[:-1])
        else:
            try:
                score = int(float(descriptor[:-1]) * 1000)
            except ValueError:
                score = 0

        candidates.append((score, url))

    if candidates:
        return candidates

    # Last-resort fallback for very simple srcset values with no descriptors.
    cleaned = srcset.strip()
    return [(0, cleaned)] if cleaned else []


def best_image_from_html(html_text: str, pet_name: Optional[str], source_photo_id: Optional[int]) -> Optional[str]:
    """
    Prefer Adopt-a-Pet's media.adoptapet.com transformed image URL from srcset.
    This matches URLs like:
    https://media.adoptapet.com/image/upload/d_Fallback-Photo_Dog-v3.png/c_fit,h_523,dpr_2/f_auto,q_auto/1310119279
    """
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[tuple[int, str]] = []

    # 1) Main pet image srcset, usually has both h_350 and h_523 versions.
    image_tags = soup.find_all("img")
    for img in image_tags:
        alt = img.get("alt")
        if pet_name and alt and alt.strip().lower() != pet_name.strip().lower():
            continue

        srcset = img.get("srcset") or img.get("srcSet")
        if srcset:
            candidates.extend(parse_srcset(srcset))

        src = img.get("src")
        if src:
            candidates.append((0, src))

    # 2) Preload imageSrcSet fallback.
    for link in soup.find_all("link"):
        as_attr = (link.get("as") or "").lower()
        if as_attr != "image":
            continue

        srcset = link.get("imagesrcset") or link.get("imageSrcSet")
        if srcset:
            candidates.extend(parse_srcset(srcset))

        href = link.get("href")
        if href:
            candidates.append((0, href))

    # Prefer media.adoptapet.com URLs, then highest width score.
    media_candidates = [(score, url) for score, url in candidates if "media.adoptapet.com" in url]
    if media_candidates:
        return max(media_candidates, key=lambda item: item[0])[1]

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    # Last-resort construction from sourcePhotoId.
    if source_photo_id:
        return (
            "https://media.adoptapet.com/image/upload/"
            "d_Fallback-Photo_Dog-v3.png/c_fit,h_523,dpr_2/f_auto,q_auto/"
            f"{source_photo_id}"
        )

    return None


def pet_id_from_html(html_text: str, pet: Optional[dict[str, Any]] = None) -> str:
    if pet and pet.get("petId"):
        return str(pet["petId"])

    soup = BeautifulSoup(html_text, "html.parser")
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        match = re.search(r"/pet/(\d+)", canonical["href"])
        if match:
            return match.group(1)

    raise ValueError("Could not determine pet ID. Pass the ID as an argument.")


def build_record(html_text: str, pet_id: Optional[str] = None) -> dict[str, Any]:
    pet = extract_pet_details(html_text)
    
    # Ensure this is a dog (petSpeciesId == 1)
    species_id = pet.get("petSpeciesId")
    if species_id is not None and species_id != 1:
        raise ValueError("NOT_A_DOG")
        
    pet_id = str(pet_id or pet_id_from_html(html_text, pet))
    url = BASE_URL.format(pet_id=pet_id)

    attrs = {
        str(item.get("label", "")).strip().lower(): item.get("content")
        for item in pet.get("petAttributes", [])
        if isinstance(item, dict)
    }

    image_url = best_image_from_html(
        html_text=html_text,
        pet_name=pet.get("petName"),
        source_photo_id=pet.get("sourcePhotoId"),
    )
    
    desc_text = clean_text(pet.get("petStory"))
    
    merged_bio = ""
    if desc_text:
        merged_bio += desc_text + "\n\n"
    merged_bio = merged_bio.strip()

    return {
        "animal_id": f"HSSA-{pet_id}",
        "shelter_profile_url": url,
        "shelter_name": clean_text(pet.get("awoName")) or LOCATED_AT_DEFAULT,
        "weight": normalize_weight(attrs.get("weight")),
        "age": title_age(attrs.get("age")),
        "more_info": "",
        "bio": merged_bio,
        "shelter_image_url": image_url,
        "city": "Tucson",
        "state": "AZ",
        "shelter_id": "HSSA",
    }


def fetch_html(pet_id: str) -> str:
    url = BASE_URL.format(pet_id=pet_id)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extension_from_response_or_url(response: requests.Response, image_url: str) -> str:
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(content_type)

    if not ext:
        ext = Path(urlparse(image_url).path).suffix

    if not ext:
        ext = ".jpg"

    if ext == ".jpe":
        ext = ".jpg"

    return ext


def download_image(image_url: Optional[str], animal_id: str, images_dir: Path) -> Optional[Path]:
    if not image_url:
        return None

    images_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(image_url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    ext = extension_from_response_or_url(response, image_url)
    output_path = images_dir / f"{animal_id}{ext}"
    output_path.write_bytes(response.content)
    return output_path


def write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pet_ids", nargs="*", help="Adopt-a-Pet numeric pet IDs, e.g. 47648753")
    parser.add_argument("--html-file", help="Optional saved HTML file to parse instead of fetching live.")
    parser.add_argument("--out", default="hssa_adoptapet_records.csv", help="CSV output path.")
    parser.add_argument("--images-dir", default="images", help="Folder where pet images will be saved.")
    parser.add_argument("--json", action="store_true", help="Print JSON records to stdout instead of writing CSV.")
    parser.add_argument("--no-download", action="store_true", help="Parse records but do not download images.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between live page requests.")
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    images_dir = Path(args.images_dir)

    if args.html_file:
        html_text = Path(args.html_file).read_text(encoding="utf-8", errors="ignore")
        pet_id = args.pet_ids[0] if args.pet_ids else None
        record = build_record(html_text, pet_id=pet_id)

        if not args.no_download:
            image_path = download_image(record["image_url"], record["animal_id"], images_dir)
            print(f"Downloaded image: {image_path}", file=sys.stderr)

        records.append(record)

    else:
        if not args.pet_ids:
            parser.error("Provide at least one pet ID or use --html-file.")

        for i, pet_id in enumerate(args.pet_ids):
            html_text = fetch_html(pet_id)
            record = build_record(html_text, pet_id=pet_id)

            if not args.no_download:
                image_path = download_image(record["image_url"], record["animal_id"], images_dir)
                print(f"Downloaded image: {image_path}", file=sys.stderr)

            records.append(record)

            if i < len(args.pet_ids) - 1:
                time.sleep(args.delay)

    if args.json:
        print(json.dumps(records, indent=2, ensure_ascii=False))
    else:
        output_path = Path(args.out)
        write_csv(records, output_path)
        print(f"Wrote {len(records)} record(s) to {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
