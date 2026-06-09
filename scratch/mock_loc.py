import sys; sys.path.insert(0, 'api')

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
