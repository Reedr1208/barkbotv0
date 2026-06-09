import os
import sys
from pathlib import Path
import subprocess

env_local = Path('.env.development.local')
if env_local.exists():
    with open(env_local) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k] = v.strip().strip('"').strip("'")

code = """
import sys
sys.path.insert(0, 'api')
from dog_meta import handler

class MockRequest:
    def makefile(self, *args, **kwargs):
        pass
    def sendall(self, *args, **kwargs):
        pass
class MockServer:
    pass

class TestHandler(handler):
    def __init__(self, path):
        self.path = path
        self.client_address = ('127.0.0.1', 80)
        self.request = MockRequest()
        self.server = MockServer()
        self.wfile = open('/dev/stdout', 'wb')
    def setup(self): pass
    def send_response(self, code, *args): print(f"[{code}]", end=" ")
    def send_header(self, *args): pass
    def end_headers(self): pass

print("Testing /dogs/la")
h = TestHandler('/?path1=la')
h.do_GET()
print()

print("Testing /dogs/la/WWLA-123 (fake id)")
h = TestHandler('/?path1=la&path2=WWLA-123')
h.do_GET()
print()
"""
with open("scratch/mock_meta.py", "w") as f: f.write(code)
subprocess.run([sys.executable, 'scratch/mock_meta.py'], env=os.environ.copy())
