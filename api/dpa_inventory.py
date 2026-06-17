import os
import sys
import subprocess
from http.server import BaseHTTPRequestHandler
import json

# Ensure subprocesses inherit the Vercel virtual environment path
os.environ['PYTHONPATH'] = os.pathsep.join(sys.path)

# Force Vercel to bundle required dependencies
try:
    import requests
    import bs4
    import supabase
except ImportError:
    pass

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            script_path = os.path.join(os.path.dirname(__file__), "..", "jobs", "dpa_inventory.py")

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=280,
                env=os.environ.copy(),
            )

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "stdout": result.stdout[-12000:] if result.stdout else "",
                "stderr": result.stderr[-12000:] if result.stderr else "",
            }).encode())

        except subprocess.CalledProcessError as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "error": str(e),
                "stdout": (e.stdout or "")[-12000:],
                "stderr": (e.stderr or "")[-12000:],
            }).encode())

        except subprocess.TimeoutExpired as e:
            self.send_response(504)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            stdout_str = e.stdout.decode('utf-8', errors='ignore') if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_str = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else (e.stderr or "")
            self.wfile.write(json.dumps({
                "status": "timeout",
                "error": "Timeout expired",
                "stdout": stdout_str[-12000:],
                "stderr": stderr_str[-12000:],
            }).encode())
