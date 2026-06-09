import sys
import os
from pathlib import Path
sys.path.insert(0, 'api')

env_local = Path('.env.development.local')
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

from random_dog import handler

class MockRequest:
    def makefile(self, *args, **kwargs): pass
    def sendall(self, *args, **kwargs): pass
class MockServer: pass

class TestHandler(handler):
    def __init__(self, path):
        self.path = path
        self.client_address = ('127.0.0.1', 80)
        self.request = MockRequest()
        self.server = MockServer()
        self.wfile = open('/dev/stdout', 'wb')
    def setup(self): pass
    def send_response(self, code, *args): print(f"\n[{code}]", end=" ")
    def send_header(self, *args): pass
    def end_headers(self): pass

h = TestHandler('/api/random_dog?location=Tucson,%20AZ%20%F0%9F%8C%B5')
h.do_GET()
