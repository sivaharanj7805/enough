"""Startup diagnostic — try importing the app and report what fails."""
import os
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

port = int(os.environ.get("PORT", 8000))
error_message = None

try:
    print("Attempting to import app.main...", flush=True)
    from app.main import app as fastapi_app
    print("Import succeeded!", flush=True)
except Exception as e:
    error_message = traceback.format_exc()
    print(f"Import FAILED:\n{error_message}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if error_message:
            import json
            body = json.dumps({"status": "error", "import_error": error_message})
        else:
            body = '{"status":"ok","import":"success"}'
        self.wfile.write(body.encode())


print(f"Diagnostic server on port {port}", flush=True)
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
