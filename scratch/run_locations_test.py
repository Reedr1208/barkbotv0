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

target_script = Path('api/locations.py').resolve()

# Mock the http server request to see output
code = """
import os
from locations import handler
class MockServer:
    def __init__(self):
        self.headers = {}
class MockRequest:
    def makefile(self, *args, **kwargs):
        pass
    def sendall(self, *args, **kwargs):
        pass
class MockHandler(handler):
    def __init__(self):
        self.client_address = ('127.0.0.1', 80)
        self.request = MockRequest()
        self.server = MockServer()
        self.wfile = open('/dev/stdout', 'wb')
        self.headers = {}
    def setup(self):
        pass
    def send_response(self, code, message=None):
        print(f"Response: {code}")
    def send_header(self, keyword, value):
        print(f"Header: {keyword}: {value}")
    def end_headers(self):
        print("End Headers")
        
h = MockHandler()
h.do_GET()
"""

with open("scratch/mock_loc.py", "w") as f:
    f.write("import sys; sys.path.insert(0, 'api')\n" + code)

subprocess.run([sys.executable, 'scratch/mock_loc.py'], env=os.environ.copy())
