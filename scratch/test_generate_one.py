import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
env_local = Path(__file__).resolve().parent.parent / ".env.development.local"
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

from api.generate_prompts import handler

class MockHandler(handler):
    def __init__(self):
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

print("Running test...")
h = MockHandler()
os.environ["MAX_EXECUTION_TIME"] = "30"  # keep it short
h.do_GET()
print(f"Status: {h.response_code}")
if h.response_code != 200:
    print(f"Error Body: {h.response_body}")
else:
    print(f"Success! Body: {h.response_body}")
