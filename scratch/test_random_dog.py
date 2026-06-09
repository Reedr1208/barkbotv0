import json
import os
import sys
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Force load .env.development.local if present
env_local = Path(__file__).resolve().parent.parent / ".env.development.local"
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'api')))
from random_dog import handler

class MockRequest:
    def makefile(self, *args, **kwargs):
        import io
        return io.BytesIO()

class MockHandler(handler):
    def __init__(self, path):
        self.path = path
        self.response_code = None
        self.headers = {}
        self.body = b""
        
        self.requestline = f"GET {path} HTTP/1.1"
        self.client_address = ("127.0.0.1", 8080)
        self.request = MockRequest()

    def send_response(self, code, message=None):
        self.response_code = code

    def send_header(self, keyword, value):
        self.headers[keyword] = value

    def end_headers(self):
        pass

    def setup(self):
        self.wfile = __import__('io').BytesIO()

    def handle(self):
        self.do_GET()
        self.body = self.wfile.getvalue()

h = MockHandler("/api/random_dog?animal_id=PACC-A865262")
h.setup()
h.handle()

try:
    print(json.dumps(json.loads(h.body.decode()), indent=2))
except:
    print(h.body.decode())
