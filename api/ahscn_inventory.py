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
    import urllib3
except ImportError:
    pass

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Run the scraper job script in the current environment
            script_path = os.path.join(os.path.dirname(__file__), "..", "jobs", "ahscn_inventory.py")
            
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr
            }).encode())
            
        except subprocess.CalledProcessError as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "error": str(e),
                "stdout": e.stdout,
                "stderr": e.stderr
            }).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "error": str(e)
            }).encode())

    def do_POST(self):
        self.do_GET()
