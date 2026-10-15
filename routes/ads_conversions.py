"""
OpenAI (ChatGPT) Ads — server-side Conversions API relay.

The browser fires each conversion through the OpenAI Measurement Pixel
(`oaiq("measure", ...)`) AND posts the same event here. We forward it to the
Conversions API so conversions still count when the pixel is blocked
(ad blockers, ITP, flaky networks). Both sides share one `event_id`, which
OpenAI uses to deduplicate pixel + server copies of the same conversion.

Env:
  OPENAI_ADS_CAPI_KEY   Conversions API key (required; relay is a no-op without it)
  OPENAI_ADS_PIXEL_ID   Pixel ID (defaults to the ChattyHound pixel)
"""

import logging
import os
import re
import time

import requests
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
logger = logging.getLogger("barkbot.ads_conversions")

DEFAULT_PIXEL_ID = "MDXmUCNodbRMkUgNZYpb3C"
CAPI_URL = "https://bzr.openai.com/v1/events"

# Only conversions configured in the OpenAI Ads dashboard are accepted.
ALLOWED_EVENTS = {"first_chat_message_sent", "shelter_link_clicked"}

_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,100}$")
_OPPREF_MAX_LEN = 512
_CANONICAL_ORIGIN = "https://chattyhound.com"

# ── Per-IP rate limit (in-memory, single replica) ────────────────────
_rate_store: dict[str, list[float]] = {}
_RATE_LIMIT = 30   # conversions per window per IP
_RATE_WINDOW = 3600


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    timestamps = [t for t in _rate_store.get(ip, []) if now - t < _RATE_WINDOW]
    if len(timestamps) >= _RATE_LIMIT:
        _rate_store[ip] = timestamps
        return True
    timestamps.append(now)
    _rate_store[ip] = timestamps
    return False


def is_configured() -> bool:
    return bool(os.environ.get("OPENAI_ADS_CAPI_KEY"))


def _client_ip(request: Request) -> str:
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else ""
    return ip


def _safe_source_url(raw: str) -> str:
    """Only forward URLs on our own site; fall back to the canonical origin."""
    raw = (raw or "").strip()[:2000]
    if raw.startswith(_CANONICAL_ORIGIN) or raw.startswith("http://localhost") or raw.startswith("http://127.0.0.1"):
        return raw
    return _CANONICAL_ORIGIN + "/"


def _send_event(event: dict) -> None:
    """Background task: POST one event to the Conversions API. Never raises."""
    api_key = os.environ.get("OPENAI_ADS_CAPI_KEY", "")
    pixel_id = os.environ.get("OPENAI_ADS_PIXEL_ID") or DEFAULT_PIXEL_ID
    try:
        resp = requests.post(
            CAPI_URL,
            params={"pid": pixel_id},
            json={"validate_only": False, "events": [event]},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChattyHound/1.0",
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.error(
                "OpenAI CAPI error %s for %s (%s): %s",
                resp.status_code, event.get("custom_event_name"), event.get("id"), resp.text[:500],
            )
        else:
            logger.info("OpenAI CAPI sent %s (%s)", event.get("custom_event_name"), event.get("id"))
    except Exception as e:
        logger.error("OpenAI CAPI request failed for %s: %s", event.get("custom_event_name"), e)


@router.post("/api/ads/conversion")
async def ads_conversion(request: Request, background_tasks: BackgroundTasks):
    """Relay a browser conversion to the OpenAI Conversions API.

    Body: {event_name, event_id, source_url?, oppref?}
    Always responds quickly (204); the upstream call runs in the background.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    event_name = (body.get("event_name") or "").strip()
    event_id = (body.get("event_id") or "").strip()
    if event_name not in ALLOWED_EVENTS or not _EVENT_ID_RE.match(event_id):
        return JSONResponse(status_code=400, content={"error": "invalid event"})

    if not is_configured():
        return Response(status_code=204)  # Pixel-only mode until the key is set

    ip = _client_ip(request)
    if _is_rate_limited(ip or "unknown"):
        return Response(status_code=204)  # Silently drop; never break the UI

    event = {
        "id": event_id,
        "type": "custom",
        "custom_event_name": event_name,
        "timestamp_ms": int(time.time() * 1000),
        "source_url": _safe_source_url(body.get("source_url") or ""),
        "action_source": "web",
        "data": {"type": "custom"},
    }

    # Click reference for attribution: browser-supplied (URL / pixel cookie),
    # falling back to the pixel's first-party cookie sent with this request.
    oppref = (body.get("oppref") or request.cookies.get("__oppref") or "").strip()
    if oppref and len(oppref) <= _OPPREF_MAX_LEN:
        event["oppref"] = oppref

    user = {}
    if ip:
        user["ip_address"] = ip
    ua = (request.headers.get("user-agent") or "").strip()
    if ua:
        user["user_agent"] = ua[:1000]
    if user:
        event["user"] = user

    background_tasks.add_task(_send_event, event)
    return Response(status_code=204)
