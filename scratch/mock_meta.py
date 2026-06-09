
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
