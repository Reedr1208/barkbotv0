import os, json
import urllib.request

env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
# Spin up a quick check by importing the handler
import sys
sys.path.append("/Users/ray/repo/Reedr1208/barkbotv0")
from api.random_dog import handler

class MockRequest:
    def makefile(self, *args, **kwargs):
        from io import BytesIO
        return BytesIO(b"GET /api/random_dog HTTP/1.1\r\n\r\n")

class MockServer:
    pass

class MockHandler(handler):
    def __init__(self):
        self.client_address = ("127.0.0.1", 80)
        self.request = MockRequest()
        self.server = MockServer()
        self.path = "/api/random_dog"
        self.headers = {}
        self.responses = []
        
    def _send_response(self, code, body):
        self.responses.append((code, body))
        
h = MockHandler()
h.do_GET()

print(h.responses[-1][1].get("animal_id"))
