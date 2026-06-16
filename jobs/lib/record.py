"""
Record hashing and diffing utilities.

Consolidates TRACKED_FIELDS, record_hash(), and compute_diff()
that were copy-pasted in every *_profiles.py and *_all.py file.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


TRACKED_FIELDS = [
    "shelter_profile_url",
    "animal_id",
    "name",
    "gender",
    "shelter_name",
    "weight",
    "age",
    "more_info",
    "bio",
    "shelter_image_url",
    "image_file",
    "image_public_url",
    "city",
    "state",
    "shelter_id",
]


def record_hash(record: Dict[str, Any], fields: List[str] | None = None) -> str:
    """Compute a SHA-256 hash of the tracked fields in a record."""
    tracked = fields or TRACKED_FIELDS
    canonical = {k: record.get(k) for k in tracked}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_diff(
    old: Optional[Dict[str, Any]],
    new: Dict[str, Any],
    fields: List[str] | None = None,
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """
    Compare old and new records on tracked fields.
    Returns (changed_field_names, {field: {"old": ..., "new": ...}}).
    """
    tracked = fields or TRACKED_FIELDS

    if not old:
        changed_fields = list(tracked)
        diff = {field: {"old": None, "new": new.get(field)} for field in changed_fields}
        return changed_fields, diff

    changed_fields: List[str] = []
    diff: Dict[str, Dict[str, Any]] = {}
    for field in tracked:
        old_val = old.get(field)
        new_val = new.get(field)
        if old_val != new_val:
            changed_fields.append(field)
            diff[field] = {"old": old_val, "new": new_val}
    return changed_fields, diff
