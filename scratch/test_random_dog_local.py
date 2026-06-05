import os
import sys
import json
from unittest.mock import MagicMock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set env vars to point to prod for testing
from pathlib import Path
env_local = Path(__file__).resolve().parent.parent / ".env.development.local"
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

from api.random_dog import handler

class MockHandler(handler):
    def __init__(self, path="/api/random_dog"):
        self.path = path
        self.response_code = None
        self.response_body = None
        self.headers = {}
    
    def send_response(self, code):
        self.response_code = code
        
    def send_header(self, key, val):
        self.headers[key] = val
        
    def end_headers(self):
        pass
        
    class WFile:
        def __init__(self, parent):
            self.parent = parent
        def write(self, bytes_data):
            self.parent.response_body = bytes_data.decode('utf-8')
            
    @property
    def wfile(self):
        if not hasattr(self, '_wfile'):
            self._wfile = self.WFile(self)
        return self._wfile

h = MockHandler()
h.do_GET()
print(f"Status: {h.response_code}")
if h.response_code != 200:
    print(f"Error Body: {h.response_body}")
else:
    print(f"Success! Body length: {len(h.response_body)}")
    try:
        data = json.loads(h.response_body)
        print(f"Intro summary: {data.get('intro_summary')}")
    except:
        pass
