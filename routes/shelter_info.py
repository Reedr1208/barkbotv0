"""
Shelter adoption info: official adoption details (fees, process, requirements,
visiting, contact, policies) for every shelter, researched once a day and
served instantly in chat.

Flow
----
1. DAILY JOB (jobs/shelter_process_details_job.py → research_shelter()):
   for each shelter with a `website_url`, one Responses call on the SAME model
   as the dog recommender (recommender.RECOMMENDER_MODEL /
   RECOMMENDER_REASONING_EFFORT) with OpenAI's built-in `web_search` tool,
   restricted to the shelter's official domain, returns a strict-JSON
   "adoption info pack". Links are validated and the pack is stored in
   `shelters.process_details` (jsonb) + `process_details_updated_at`.
2. CHAT (routes/api_routes.py): when the user asks about adoption logistics the
   dog's own profile doesn't answer, the dog model calls the `find_shelter_info`
   function tool → get_shelter_info() reads the stored pack (one DB read, no web
   search) and the dog answers in character.

Guardrails
----------
• At most one research call per shelter per day; nothing user-triggered hits the web.
• A failed / empty research run never overwrites a previously good pack.
• get_shelter_info() never raises: with no pack the dog still links the official site.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from routes import recommender

logger = logging.getLogger("barkbot.shelter_info")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Same model as the dog recommender agent (by design — one "agent" model to tune).
SHELTER_INFO_MODEL = recommender.RECOMMENDER_MODEL
SHELTER_INFO_REASONING_EFFORT = recommender.RECOMMENDER_REASONING_EFFORT

# Offline daily job → we can afford a thorough search.
RESEARCH_TIMEOUT_SECONDS = 180
RESEARCH_MAX_SEARCHES = 6
RESEARCH_MAX_OUTPUT_TOKENS = 4000
MAX_LINKS = 6
MAX_LIST_ITEMS = 8

# A pack older than this is still served, but flagged so the dog hedges more.
STALE_AFTER_DAYS = 7


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  URL / TEXT HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _http_url(v: Any) -> str:
    v = v.strip() if isinstance(v, str) else ""
    return v if re.match(r"^https?://", v, re.I) else ""


def _host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _strip_tracking(url: str) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_")]
    return urlunparse(p._replace(query=urlencode(q)))


def _normalize_url(url: str) -> str:
    return _strip_tracking(url).rstrip("/").lower()


_MD_CITATION_RE = re.compile(r"\s*\(\s*\[[^\]]*\]\([^)]*\)\s*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((?:https?://)[^)]*\)")
_BARE_URL_RE = re.compile(r"\s*\(?https?://\S+\)?")


def _clean_text(s: Any, limit: int = 400) -> str:
    """Plain text only: drop inline citations, markdown links and bare URLs."""
    if not isinstance(s, str):
        return ""
    s = _MD_CITATION_RE.sub("", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _BARE_URL_RE.sub("", s)
    return " ".join(s.split())[:limit]


def _clean_list(items: Any, limit: int = 300) -> list[str]:
    out = [_clean_text(s, limit) for s in (items if isinstance(items, list) else [])]
    return [s for s in out if s][:MAX_LIST_ITEMS]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DAILY RESEARCH (called by jobs/shelter_process_details_job.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}

PACK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "found_official_info": {"type": "boolean"},
        "overview": _STR,
        "fees": _STR,
        "process_steps": _STR_LIST,
        "application": _STR,
        "timeline": _STR,
        "requirements": _STR_LIST,
        "visiting": _STR,
        "policies": _STR_LIST,
        "contact": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"phone": _STR, "email": _STR, "address": _STR, "hours": _STR},
            "required": ["phone", "email", "address", "hours"],
        },
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": _STR, "url": _STR},
                "required": ["title", "url"],
            },
        },
    },
    "required": ["found_official_info", "overview", "fees", "process_steps", "application", "timeline",
                 "requirements", "visiting", "policies", "contact", "links"],
}

RESEARCH_INSTRUCTIONS = """You compile the official DOG adoption information for one animal shelter / rescue. A chat assistant will use your result to answer would-be adopters' questions for the next day, so be thorough. Today's date is {today}.

Use web search on the organization's official website (several searches are fine: adopt page, adoption process, fees, FAQ, contact/hours, policies). Rules:
- Report ONLY facts you found on the organization's own pages. Never guess or fill gaps from general knowledge. Leave a field empty ("" or []) when you didn't find it.
- Make sure the info is for THIS organization and location (some shelter names are shared).
- Dogs only — skip cat-specific details.
- Fields:
  • overview: 1–2 sentences on how adopting from them works (e.g. foster-based rescue with no facility; walk-in county shelter).
  • fees: the dog adoption fee schedule as published (tiers by age/size, what's included, current specials and their dates, licensing fees).
  • process_steps: the adoption steps in order (apply, review/interview, meet, home visit, contract/payment, pickup …).
  • application: how and where to apply (online form, in person, waitlist) and anything notable about it.
  • timeline: how long the process usually takes, response times.
  • requirements: adopter requirements (minimum age, ID, landlord approval, residency/region, fenced yard, meeting resident pets, home visit …).
  • visiting: how to meet dogs (walk-in hours, appointment only, foster homes, adoption events, locations).
  • policies: other adopter-relevant policies (returns, holds/reservations, out-of-state adoption, foster-to-adopt, transport, trial periods).
  • contact: main adoption phone, email, street address and adoption hours.
- found_official_info: true only if you found relevant adoption info on the official site.
- Plain text in every field: no markdown, no inline citations, no URLs (URLs go only in `links`).
- links: up to 6 of the most useful official pages (adoption process, application, fees, FAQ, contact, adoptable dogs) with short human titles. Copy exact URLs from your search results.
- Concise: each string ≤ 350 characters, at most 8 items per list."""


def _collect_sources(resp) -> set[str]:
    """Every URL the web search returned or the model cited (normalized)."""
    out: set[str] = set()
    for item in getattr(resp, "output", None) or []:
        t = getattr(item, "type", "")
        if t == "web_search_call":
            action = getattr(item, "action", None)
            for src in (getattr(action, "sources", None) or []):
                if getattr(src, "url", None):
                    out.add(_normalize_url(src.url))
        elif t == "message":
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    if getattr(ann, "url", None):
                        out.add(_normalize_url(ann.url))
    return out


def _validate_links(raw_links: Any, allowed_hosts: set[str], sources: set[str]) -> list[dict]:
    """Keep links on the official domain or that the search actually returned; strip tracking params."""
    links, seen = [], set()
    for link in raw_links if isinstance(raw_links, list) else []:
        if not isinstance(link, dict):
            continue
        url = _http_url(link.get("url"))
        if not url:
            continue
        url = _strip_tracking(url)
        host = _host(url)
        on_allowed = any(host == h or host.endswith("." + h) for h in allowed_hosts)
        key = _normalize_url(url)
        if not (on_allowed or key in sources) or key in seen:
            continue
        seen.add(key)
        links.append({"title": _clean_text(link.get("title"), 80) or host, "url": url})
        if len(links) >= MAX_LINKS:
            break
    return links


def research_shelter(openai_client, shelter: dict) -> tuple[dict, dict]:
    """
    Research one `shelters` row. Returns (pack, meta); raises on API errors.
    pack["found"] is False when nothing usable was found (callers must not store it
    over an existing good pack).
    """
    official = _http_url(shelter.get("website_url"))
    official_host = _host(official)
    tool: dict = {"type": "web_search", "search_context_size": "medium"}
    if official_host:
        tool["filters"] = {"allowed_domains": [official_host]}

    payload = {
        "organization": shelter.get("shelter_name") or shelter.get("shelter_id"),
        "location": ", ".join(x for x in (shelter.get("city"), shelter.get("state")) if x),
        "official_website": official or "unknown — identify the organization's own website",
    }
    resp = openai_client.responses.create(
        model=SHELTER_INFO_MODEL,
        instructions=RESEARCH_INSTRUCTIONS.format(today=datetime.now(timezone.utc).strftime("%B %d, %Y")),
        input=json.dumps(payload, ensure_ascii=False),
        tools=[tool],
        max_tool_calls=RESEARCH_MAX_SEARCHES,
        include=["web_search_call.action.sources"],
        reasoning={"effort": SHELTER_INFO_REASONING_EFFORT},
        text={"format": {"type": "json_schema", "name": "shelter_adoption_info", "strict": True,
                         "schema": PACK_SCHEMA}},
        max_output_tokens=RESEARCH_MAX_OUTPUT_TOKENS,
        store=False,
        timeout=RESEARCH_TIMEOUT_SECONDS,
    )
    raw = json.loads(resp.output_text or "{}")
    sources = _collect_sources(resp)
    contact = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
    pack = {
        "overview": _clean_text(raw.get("overview")),
        "fees": _clean_text(raw.get("fees"), 600),
        "process_steps": _clean_list(raw.get("process_steps")),
        "application": _clean_text(raw.get("application")),
        "timeline": _clean_text(raw.get("timeline")),
        "requirements": _clean_list(raw.get("requirements")),
        "visiting": _clean_text(raw.get("visiting")),
        "policies": _clean_list(raw.get("policies")),
        "contact": {k: _clean_text(contact.get(k), 200) for k in ("phone", "email", "address", "hours")},
        "links": _validate_links(raw.get("links"), {official_host} if official_host else set(), sources),
    }
    facts = [v for k, v in pack.items() if k not in ("links", "contact") and v] + \
            [v for v in pack["contact"].values() if v]
    pack["found"] = bool(raw.get("found_official_info")) and len(facts) >= 2

    usage = getattr(resp, "usage", None)
    meta = {
        "shelter_id": shelter.get("shelter_id"),
        "model": SHELTER_INFO_MODEL,
        "searches": sum(1 for o in resp.output if getattr(o, "type", "") == "web_search_call"),
        "sources": len(sources),
        "fields": len(facts),
        "links": len(pack["links"]),
        "found": pack["found"],
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }
    return pack, meta


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CHAT-TIME LOOKUP (called by the find_shelter_info tool)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_configured() -> bool:
    # Chat-time lookup is a plain DB read — always available.
    return True


def get_shelter_info(sb, animal_id: str) -> dict:
    """
    Blocking; never raises. Returns:
      {status: ok|not_found|error, shelter_id, shelter_name, official_site,
       dog_listing, last_checked, stale, info (dict|None)}
    """
    result = {"status": "error", "shelter_id": None, "shelter_name": "", "official_site": "",
              "dog_listing": "", "last_checked": None, "stale": False, "info": None}
    try:
        a = sb.table("animals").select("shelter_id, shelter_name, shelter_profile_url") \
            .eq("animal_id", animal_id).limit(1).execute().data
        if a:
            result.update(shelter_id=a[0].get("shelter_id"), shelter_name=a[0].get("shelter_name") or "",
                          dog_listing=_http_url(a[0].get("shelter_profile_url")))
        if not result["shelter_id"]:
            result["status"] = "not_found"
            return result
        # select("*") so this still works if the newer columns haven't been migrated yet
        s = sb.table("shelters").select("*").eq("shelter_id", result["shelter_id"]).limit(1).execute().data
        s = s[0] if s else {}
        result["shelter_name"] = s.get("shelter_name") or result["shelter_name"]
        result["official_site"] = _http_url(s.get("website_url"))
        pack = s.get("process_details")
        if isinstance(pack, str):
            pack = json.loads(pack)
        updated = s.get("process_details_updated_at")
        if updated:
            try:
                ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                result["last_checked"] = ts.date().isoformat()
                result["stale"] = (datetime.now(timezone.utc) - ts).days >= STALE_AFTER_DAYS
            except ValueError:
                pass
        if isinstance(pack, dict) and pack.get("found"):
            result.update(status="ok", info=pack)
        else:
            result["status"] = "not_found"
        return result
    except Exception:
        logger.exception("shelter_info: lookup failed")
        result["status"] = "error"
        return result
