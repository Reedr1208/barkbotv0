import os
import subprocess
import sys
import logging
from pathlib import Path
from http.server import BaseHTTPRequestHandler

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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        logging.info("Starting up scrape_muddypaws handler...")

        auth_header = self.headers.get("Authorization")
        cron_secret = os.environ.get("CRON_SECRET")
        if cron_secret:
            expected = f"Bearer {cron_secret}"
            if auth_header != expected:
                logging.warning("Unauthorized access attempt to scrape_muddypaws.")
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Unauthorized")
                return
        
        target_script = Path(__file__).resolve().parent.parent / "jobs" / "mp_all.py"
        python_exe = sys.executable

        try:
            logging.info(f"Running command: {python_exe} {target_script}")
            result = subprocess.run([python_exe, str(target_script)], env=os.environ.copy(), capture_output=True, text=True)
            
            if result.returncode == 0:
                logging.info(f"Subprocess completed successfully.\nStdout: {result.stdout}")
                if result.stderr:
                    logging.warning(f"Stderr: {result.stderr}")
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Job completed successfully")
            else:
                logging.error(f"Subprocess failed with code {result.returncode}.\nStdout: {result.stdout}\nStderr: {result.stderr}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Job failed")
        except Exception as e:
            logging.error(f"Failed to spawn subprocess: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
