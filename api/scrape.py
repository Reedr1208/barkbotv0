import json
import os
import subprocess
import sys
import logging
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Configure basic logging so Vercel can capture it nicely
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

MANUAL_RUN_SECRET = os.getenv("MANUAL_RUN_SECRET")
CRON_SECRET = os.getenv("CRON_SECRET")


class handler(BaseHTTPRequestHandler):
    def _authorized(self):
        auth = self.headers.get("authorization") or self.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            logging.error("Authorization header is missing or malformed.")
            return False
        token = auth.split(" ", 1)[1]
        is_valid = token in {MANUAL_RUN_SECRET, CRON_SECRET}
        if not is_valid:
            logging.error("Token is invalid.")
        return is_valid

    def do_GET(self):
        logging.info("Starting up cron handler...")
        
        if not self._authorized():
            self.send_response(401)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Unauthorized"}).encode('utf-8'))
            return

        script1_path = Path(__file__).resolve().parent.parent / "01_scrape_all_dogs.py"
        script2_path = Path(__file__).resolve().parent.parent / "02_scrape_detailed_dogs.py"
        logging.info(f"Python executable: {sys.executable}")
        
        # Check required env vars to log if they are missing
        required_vars = ["storage_SUPABASE_URL", "storage_SUPABASE_SERVICE_ROLE_KEY"]
        missing = [v for v in required_vars if v not in os.environ]
        if missing:
            logging.error(f"Missing required env vars: {missing}")
        else:
            logging.info("All required SUPABASE env vars are present.")
            
        def run_script(script_path, extra_args=None, timeout=140):
            cmd = [sys.executable, str(script_path)] + (extra_args or [])
            logging.info(f"Running command: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
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
            return proc

        try:
            logging.info("--- Running 01_scrape_all_dogs.py ---")
            proc1 = run_script(script1_path, timeout=120)
            
            proc2 = None
            if proc1.returncode == 0:
                logging.info("--- Running 02_scrape_detailed_dogs.py ---")
                proc2 = run_script(script2_path, ["--triggered-by", "vercel_api"], timeout=160)
            else:
                logging.error("Skipping 02_scrape_detailed_dogs.py because 01_scrape_all_dogs.py failed.")
            
            final_code = proc2.returncode if proc2 else proc1.returncode
            statusCode = 200 if final_code == 0 else 500
            body = {
                "ok": final_code == 0,
                "returncode": final_code,
                "stdout_1": proc1.stdout[-6000:] if proc1.stdout else "",
                "stderr_1": proc1.stderr[-6000:] if proc1.stderr else "",
                "stdout_2": (proc2.stdout[-6000:] if proc2.stdout else "") if proc2 else "",
                "stderr_2": (proc2.stderr[-6000:] if proc2.stderr else "") if proc2 else "",
            }
        except subprocess.TimeoutExpired as e:
            statusCode = 504
            logging.error(f"Subprocess timed out after 55 seconds.")
            stdout_str = e.stdout.decode('utf-8', errors='ignore') if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_str = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else (e.stderr or "")
            
            if stdout_str:
                logging.info("--- STDOUT (Timeout) ---")
                for line in stdout_str.splitlines()[-50:]:
                    logging.info(line)
            if stderr_str:
                logging.error("--- STDERR (Timeout) ---")
                for line in stderr_str.splitlines()[-50:]:
                    logging.error(line)
                    
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

