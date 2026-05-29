import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Force env vars for test
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
os.environ["CRON_SECRET"] = "test_secret_123"

# Import handler
from api.scrape_all import handler

mock_req = MagicMock()
mock_req.makefile.return_value = MagicMock()

class MockHandler(handler):
    def __init__(self):
        self.headers = {"Authorization": "Bearer test_secret_123"}
        self.wfile = MagicMock()
    
    def send_response(self, code): pass
    def send_header(self, k, v): pass
    def end_headers(self): pass

h = MockHandler()
h.do_GET()
print("Scrape all handler successfully executed.")
