"""
Shelter URL slugs — single source of truth for name-based shelter slugs.

Shelter-scoped URLs nest a slug derived from ``shelters.shelter_name`` under
the location slug (``shelters.relative_path``):

    /nyc/bideawee                      shareable shelter landing link
    /dogs/nyc/bideawee                 shelter scope, no dog yet
    /dogs/nyc/bideawee/BDW-123         browsing a dog with the shelter filter on

Dog share links (Share button) stay location-only (``/dogs/nyc/BDW-123``).

Slugs are unique per location. On the (unlikely) event two shelters in the
same location slugify identically, the later one (by shelter_id) gets its
lower-cased shelter_id appended.
"""

import re
import time
import unicodedata

_CACHE_TTL_SECONDS = 300
_index_cache = {"at": 0.0, "by_path": None, "by_id": None}


def slugify_shelter_name(name):
    """'Wags & Walks LA' → 'wags-walks-la'; 'San Francisco SPCA' → 'san-francisco-spca'."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"['’`]", "", s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _loc_slug(relative_path):
    return (relative_path or "").strip("/").lower()


def build_shelter_slug_index(rows):
    """
    Build lookup maps from shelter rows (needs shelter_id, shelter_name,
    location_display_name, relative_path).

    Returns (by_path, by_id):
      by_path: {(loc_slug, shelter_slug): entry}
      by_id:   {shelter_id: entry}
    where entry = {shelter_id, name, slug, location, relative_path}.
    """
    by_path, by_id = {}, {}
    for row in sorted(rows or [], key=lambda r: r.get("shelter_id") or ""):
        sid = row.get("shelter_id")
        rp = row.get("relative_path") or ""
        loc = _loc_slug(rp)
        if not sid or not loc:
            continue
        slug = slugify_shelter_name(row.get("shelter_name") or sid) or sid.lower()
        if (loc, slug) in by_path:
            slug = f"{slug}-{sid.lower()}"
        entry = {
            "shelter_id": sid,
            "name": row.get("shelter_name") or sid,
            "slug": slug,
            "location": row.get("location_display_name") or "",
            "relative_path": rp,
        }
        by_path[(loc, slug)] = entry
        by_id[sid] = entry
    return by_path, by_id


def get_shelter_slug_index(client=None):
    """Cached (5 min) slug index loaded from the shelters table."""
    now = time.time()
    if _index_cache["by_path"] is not None and now - _index_cache["at"] < _CACHE_TTL_SECONDS:
        return _index_cache["by_path"], _index_cache["by_id"]
    try:
        if client is None:
            from routes.deps import get_supabase_client
            client = get_supabase_client()
        res = client.table("shelters").select(
            "shelter_id, shelter_name, location_display_name, relative_path"
        ).execute()
        by_path, by_id = build_shelter_slug_index(res.data or [])
        _index_cache.update({"at": now, "by_path": by_path, "by_id": by_id})
        return by_path, by_id
    except Exception:
        # Serve stale data rather than nothing if the DB hiccups.
        return _index_cache["by_path"] or {}, _index_cache["by_id"] or {}


def resolve_shelter_slug(location_slug, shelter_slug, client=None):
    """Return the shelter entry for /<location_slug>/<shelter_slug>, or None."""
    by_path, _ = get_shelter_slug_index(client)
    return by_path.get(((location_slug or "").strip("/").lower(), (shelter_slug or "").strip("/").lower()))
