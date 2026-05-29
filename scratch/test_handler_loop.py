import os, json
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
with open(env_file, "r") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            
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
        self.responses = []
        
    def setup(self):
        pass
        
    def handle_one_request(self):
        self.path = "/api/random_dog"
        self.headers = {}
        self.do_GET()
        
    def _send_response(self, code, body):
        self.responses.append((code, body))

results = {"PIMA": 0, "MUDDYPAWS": 0}
for i in range(20):
    h = MockHandler()
    h.handle_one_request()
    body = h.responses[-1][1]
    loc = body.get("located_at", "").lower()
    if "pima" in loc:
        results["PIMA"] += 1
    elif "muddy" in loc:
        results["MUDDYPAWS"] += 1
    else:
        print("Unknown loc:", loc)
        
print("RESULTS:", results)
