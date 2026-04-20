import json
import os
import subprocess
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler

MANUAL_RUN_SECRET = os.getenv("MANUAL_RUN_SECRET")
CRON_SECRET = os.getenv("CRON_SECRET")


class handler(BaseHTTPRequestHandler):
    def _authorized(self):
        auth = self.headers.get("authorization") or self.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return False
        token = auth.split(" ", 1)[1]
        return token in {MANUAL_RUN_SECRET, CRON_SECRET}

    def do_GET(self):
        if not self._authorized():
            self.send_response(401)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Unauthorized"}).encode('utf-8'))
            return

        script_path = Path(__file__).resolve().parent.parent / "scrape_24petconnect_supabase.py"
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path), "--triggered-by", "vercel_api"],
                capture_output=True,
                text=True,
                timeout=55,
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

        self.send_response(statusCode)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))

    def do_POST(self):
        self.do_GET()
