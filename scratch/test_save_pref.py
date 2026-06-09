import os
import json
import urllib.request

req = urllib.request.Request(
    'http://localhost:3000/api/save_preferences',
    data=json.dumps({"email": "test@example.com", "location": "Tucson, AZ 🌵"}).encode(),
    headers={"Content-Type": "application/json"}
)
try:
    resp = urllib.request.urlopen(req)
    print(resp.read().decode())
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print(e.read().decode())
