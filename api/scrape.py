import json
import os
import subprocess
import sys
from pathlib import Path

MANUAL_RUN_SECRET = os.getenv("MANUAL_RUN_SECRET")
CRON_SECRET = os.getenv("CRON_SECRET")


def _authorized(headers):
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return False
    token = auth.split(" ", 1)[1]
    return token in {MANUAL_RUN_SECRET, CRON_SECRET}


def handler(request):
    headers = getattr(request, "headers", {}) or {}
    if not _authorized(headers):
        return {
            "statusCode": 401,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": False, "error": "Unauthorized"}),
        }

    script_path = Path(__file__).resolve().parent.parent / "scrape_24petconnect_supabase.py"
    proc = subprocess.run(
        [sys.executable, str(script_path), "--triggered-by", "vercel_api"],
        capture_output=True,
        text=True,
        timeout=290,
        env=os.environ.copy(),
    )

    body = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }
    return {
        "statusCode": 200 if proc.returncode == 0 else 500,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
