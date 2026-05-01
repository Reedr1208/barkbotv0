import json
import os
import subprocess
import sys
import logging
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Configure basic logging so Vercel can capture it nicely
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

MANUAL_RUN_SECRET = "test_secret_123"
CRON_SECRET = os.getenv("CRON_SECRET")


# Force load .env.local if present to bypass Vercel CLI bugs
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
            logging.error("Authorization header is missing or malformed.")
            return False
        token = auth.split(" ", 1)[1]
        
        # Read dynamically
        manual_secret = os.getenv("MANUAL_RUN_SECRET")
        cron_secret = os.getenv("CRON_SECRET")
        
        is_valid = token in {manual_secret, cron_secret}
        if not is_valid:
            logging.error("Token is invalid.")
        return is_valid

    def do_GET(self):
        logging.info("Starting up scrape_all handler...")
        
        if not self._authorized():
            self.send_response(401)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Unauthorized"}).encode('utf-8'))
            return

        script_path = Path(__file__).resolve().parent.parent / "01_scrape_all_dogs.py"
        logging.info(f"Target script path: {script_path}")
        logging.info(f"Python executable: {sys.executable}")
        
        # Check required env vars to log if they are missing
        required_vars = ["storage_SUPABASE_URL", "storage_SUPABASE_SERVICE_ROLE_KEY"]
        missing = [v for v in required_vars if v not in os.environ]
        if missing:
            logging.error(f"Missing required env vars: {missing}")
        else:
            logging.info("All required SUPABASE env vars are present.")
            
        try:
            cmd = [sys.executable, str(script_path)]
            logging.info(f"Running command: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=240,
                env=os.environ.copy(),
            )
            statusCode = 200 if proc.returncode == 0 else 500
            
            if proc.returncode != 0:
                logging.error(f"Subprocess failed with returncode {proc.returncode}")
            else:
                logging.info(f"Subprocess succeeded (returncode 0)")
            
            if proc.stdout:
                logging.info("--- STDOUT ---")
                for line in proc.stdout.splitlines()[-50:]:  # Print last 50 lines
                    logging.info(line)
            if proc.stderr:
                logging.error("--- STDERR ---")
                for line in proc.stderr.splitlines()[-50:]:
                    logging.error(line)
                    
            body = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:] if proc.stdout else "",
                "stderr": proc.stderr[-12000:] if proc.stderr else "",
            }
        except subprocess.TimeoutExpired as e:
            statusCode = 504
            logging.error(f"Subprocess timed out.")
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
            logging.exception("An unexpected error occurred while executing the subprocess.")
            body = {
                "ok": False,
                "returncode": -1,
                "error": str(e)
            }

        logging.info(f"Returning HTTP {statusCode}")
        self.send_response(statusCode)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))

    def do_POST(self):
        self.do_GET()
