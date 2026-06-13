import json
import os
import subprocess
import sys
import logging
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Ensure subprocesses inherit the Vercel virtual environment path
os.environ['PYTHONPATH'] = os.pathsep.join(sys.path)


# Force Vercel to bundle required dependencies
try:
    import requests
    import bs4
    import supabase
    import playwright
    import openai
    import pydantic
except ImportError:
    pass


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

env_local = Path(__file__).resolve().parent.parent / ".env.local"
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v

class handler(BaseHTTPRequestHandler):
    def _authorized(self):
        auth = self.headers.get("authorization") or self.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return False
        token = auth.split(" ", 1)[1]
        manual_secret = os.getenv("MANUAL_RUN_SECRET")
        cron_secret = os.getenv("CRON_SECRET")
        return token in {manual_secret, cron_secret}

    def do_GET(self):
        if not self._authorized():
            self.send_response(401)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Unauthorized"}).encode('utf-8'))
            return

        script_path = Path(__file__).resolve().parent.parent / "jobs" / "pawsch_profiles.py"
        try:
            cmd = [sys.executable, str(script_path)]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=290,
                env=os.environ.copy(),
            )
            statusCode = 200 if proc.returncode == 0 else 500
            body = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:] if proc.stdout else "",
                "stderr": proc.stderr[-12000:] if proc.stderr else "",
            }
        except subprocess.TimeoutExpired as e:
            statusCode = 504
            stdout_str = e.stdout.decode('utf-8', errors='ignore') if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_str = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else (e.stderr or "")
            body = {
                "ok": False,
                "returncode": -1,
                "error": "Timeout expired",
                "stdout": stdout_str[-12000:],
                "stderr": stderr_str[-12000:],
            }
        except Exception as e:
            statusCode = 500
            body = {"ok": False, "returncode": -1, "error": str(e)}

        self.send_response(statusCode)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))

    def do_POST(self):
        self.do_GET()
