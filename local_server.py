import os
import sys
import http.server
import socketserver
from urllib.parse import urlparse

# Load .env.local environment variables if present
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                os.environ[key] = val

# Ensure parent and workspace folders are on path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

PORT = 8085
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static assets from the public/ folder by default
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _send_response(self, status_code, body):
        import json
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode('utf-8'))

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path.startswith("/api/"):
            api_routes = {
                "random_dog": "api.random_dog",
                "save_preferences": "api.save_preferences",
                "login": "api.login",
                "chat": "api.chat"
            }
            api_name = parsed_url.path.split("/")[-1]
            if api_name in api_routes:
                module_name = api_routes[api_name]
                try:
                    module = __import__(module_name, fromlist=["handler"])
                    # Delegate directly to Vercel handler
                    module.handler.do_GET(self)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    import json
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_error(404, f"API {api_name} not found")
        else:
            # Fall back to standard SimpleHTTPRequestHandler static files serving
            super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path.startswith("/api/"):
            api_routes = {
                "random_dog": "api.random_dog",
                "save_preferences": "api.save_preferences",
                "login": "api.login",
                "chat": "api.chat"
            }
            api_name = parsed_url.path.split("/")[-1]
            if api_name in api_routes:
                module_name = api_routes[api_name]
                try:
                    module = __import__(module_name, fromlist=["handler"])
                    # Delegate directly to Vercel handler
                    module.handler.do_POST(self)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    import json
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_error(404, f"API {api_name} not found")
        else:
            self.send_error(405, "Method not allowed")

if __name__ == "__main__":
    # Prevent socket address reuse errors on quick restarts
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        print(f"🚀 Local Mock Server active at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
