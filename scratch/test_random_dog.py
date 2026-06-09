import urllib.parse
from http.server import BaseHTTPRequestHandler
import sys
import os

# Mock self and execute random_dog logic roughly
import api.random_dog
from api.random_dog import handler

class MockRequest:
    def __init__(self):
        self.path = "/api/random_dog?location=" + urllib.parse.quote("Tucson, AZ 🌵")

class MockHandler(handler):
    def __init__(self):
        self.path = MockRequest().path
        self.sent_status = None
        self.sent_body = None

    def _send_response(self, code, body):
        self.sent_status = code
        self.sent_body = body

h = MockHandler()
h.do_GET()

print(f"Status: {h.sent_status}")
if h.sent_body and "animal_id" in h.sent_body:
    print(f"Found dog: {h.sent_body['animal_id']}")
    print(f"Matched location: {h.sent_body.get('match_details', {}).get('location')}")
else:
    print(h.sent_body)
