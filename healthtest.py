"""Minimal health server to debug Railway deployment."""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

port = int(os.environ.get("PORT", 8000))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","test":"minimal"}')


print(f"Minimal health server on port {port}", flush=True)
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
