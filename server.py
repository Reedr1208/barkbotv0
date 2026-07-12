"""
BarkBot FastAPI Server — Entry point for Railway deployment.

Replaces the Vercel serverless function architecture with a single
persistent FastAPI application that:
- Serves all API routes (JSON endpoints)
- Serves the /dogs/ SSR pages (OG meta injection)
- Serves static files from public/
- Runs APScheduler for all cron jobs
"""

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

# CORS — allow all origins (same as the previous Access-Control-Allow-Origin: *)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    app.mount("/js", StaticFiles(directory=os.path.join(PUBLIC_DIR, "js")), name="js")
    app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static_assets")


# ── Catch-all: serve index.html for SPA routes ─────────────────────

@app.get("/privacy.html")
async def privacy():
    """Serve the privacy policy page."""
    path = os.path.join(PUBLIC_DIR, "privacy.html")
    if os.path.isfile(path):
        return FileResponse(path, media_type="text/html")
    return HTMLResponse("Not found", status_code=404)


@app.get("/{filename:path}")
async def serve_static_or_spa(filename: str, request: Request):
    """
    Serve static files from public/ if they exist, otherwise serve
    index.html for SPA client-side routing.
    """
    # Try to serve the file directly from public/
    file_path = os.path.join(PUBLIC_DIR, filename)
    if filename and os.path.isfile(file_path):
        # Determine content type
        if filename.endswith(".css"):
            return FileResponse(file_path, media_type="text/css")
        elif filename.endswith(".js"):
            return FileResponse(file_path, media_type="application/javascript")
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

    # Fallback: serve index.html (SPA routing)
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")

    return HTMLResponse("Not found", status_code=404)
