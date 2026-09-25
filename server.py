"""
BarkBot FastAPI Server — Entry point for Railway deployment.

A persistent FastAPI application that:
- Serves all API routes (JSON endpoints)
- Serves the /dogs/ SSR pages (OG meta injection)
- Serves static files from public/
- Runs APScheduler for all cron jobs
"""

import json
import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

# Configure logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("barkbot")

# Ensure the project root is on sys.path so jobs.shelters.* imports work
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler on startup, shut it down on shutdown."""
    from scheduler import scheduler, setup_schedules

    setup_schedules()
    scheduler.start()
    logger.info("APScheduler started.")

    yield

    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped.")


app = FastAPI(
    title="BarkBot API",
    description="ChattyHound backend — adoptable dog chat + scraper platform",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — restrict to allowed origins in production
_allowed_origins_str = os.environ.get("ALLOWED_ORIGINS", "")
if _allowed_origins_str:
    _allowed_origins = [o.strip() for o in _allowed_origins_str.split(",") if o.strip()]
else:
    # Local development fallback
    _allowed_origins = ["*"]
    logger.warning("CORS: ALLOWED_ORIGINS not set — allowing all origins (dev mode).")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers (CSP + more) ──────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: StarletteResponse = await call_next(request)
        # Content-Security-Policy — allow our CDN deps, Google Analytics, and Google Ads
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'"
            " https://cdn.jsdelivr.net"
            " https://www.googletagmanager.com"
            " https://www.google-analytics.com"
            " https://analytics.google.com"
            " https://www.google.com"
            " https://www.googleadservices.com"
            " https://googleads.g.doubleclick.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https: blob:",
            "connect-src 'self'"
            " https://www.google-analytics.com"
            " https://analytics.google.com"
            " https://www.googletagmanager.com"
            " https://www.google.com"
            " https://www.googleadservices.com"
            " https://googleads.g.doubleclick.net",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ])
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── Register route modules ──────────────────────────────────────────

from routes.api_routes import router as api_router
from routes.dog_meta_routes import router as dog_meta_router
from routes.cron_routes import router as cron_router
from routes.admin_routes import router as admin_router

app.include_router(api_router)
app.include_router(dog_meta_router)
app.include_router(cron_router)
app.include_router(admin_router)

# ── Static files ────────────────────────────────────────────────────
# Mount public/ directory for CSS, JS, images. This must come AFTER
# the API routes so /api/* paths are matched first.

PUBLIC_DIR = os.path.join(PROJECT_ROOT, "public")
if os.path.isdir(PUBLIC_DIR):
    # JS files served via catch-all handler with no-cache headers (see serve_static_or_spa)
    app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static_assets")


# ── Cache for known location slugs → display_name ──────────────────

_LOCATION_SLUG_CACHE = None  # {slug: display_name}


def _get_location_slugs():
    """Load and cache the slug→display_name map from the shelters table."""
    global _LOCATION_SLUG_CACHE
    if _LOCATION_SLUG_CACHE is not None:
        return _LOCATION_SLUG_CACHE

    try:
        from routes.deps import get_supabase_client
        sb = get_supabase_client()
        res = sb.table("shelters").select("relative_path, location_display_name").execute()
        slugs = {}
        for row in res.data:
            rp = row.get("relative_path", "")
            dn = row.get("location_display_name", "")
            if rp and dn:
                slug = rp.lstrip("/").lower()
                if slug and slug not in slugs:
                    slugs[slug] = dn
        _LOCATION_SLUG_CACHE = slugs
        return slugs
    except Exception:
        return {}


@app.get("/{filename:path}")
async def serve_static_or_spa(filename: str, request: Request):
    """
    Serve static files from public/ if they exist, otherwise serve
    index.html for SPA client-side routing.
    For known location slugs (e.g. /tucson), inject city data into the HTML.
    """
    # Try to serve the file directly from public/
    file_path = os.path.join(PUBLIC_DIR, filename)
    if filename and os.path.isfile(file_path):
        # Determine content type
        if filename.endswith(".css"):
            return FileResponse(file_path, media_type="text/css", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        elif filename.endswith(".js"):
            return FileResponse(file_path, media_type="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        elif filename.endswith(".png"):
            return FileResponse(file_path, media_type="image/png")
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            return FileResponse(file_path, media_type="image/jpeg")
        elif filename.endswith(".html"):
            return FileResponse(file_path, media_type="text/html")
        elif filename.endswith(".ico"):
            return FileResponse(file_path, media_type="image/x-icon")
        elif filename.endswith(".svg"):
            return FileResponse(file_path, media_type="image/svg+xml")
        elif filename.endswith(".webp"):
            return FileResponse(file_path, media_type="image/webp")
        return FileResponse(file_path)

    # Check if this is a known location slug (e.g. /tucson → "Tucson, AZ 🌵")
    slug = filename.strip("/").lower()
    if slug and "/" not in slug:
        location_slugs = _get_location_slugs()
        display_name = location_slugs.get(slug)
        if display_name:
            index_path = os.path.join(PUBLIC_DIR, "index.html")
            if os.path.isfile(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                # Inject city data into the HTML
                bootstrap = (
                    f'<script>window.__CH_DETECTED_CITY__={json.dumps(display_name)};'
                    f'window.__CH_INITIAL_LOCATION__={json.dumps("/" + slug)};</script>\n'
                )
                html_content = html_content.replace("<body>", f"<body>\n{bootstrap}", 1)
                return HTMLResponse(content=html_content, headers={"Cache-Control": "public, max-age=300"})

    # Fallback: serve index.html (SPA routing)
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")

    return HTMLResponse("Not found", status_code=404)

