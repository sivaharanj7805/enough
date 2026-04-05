"""Startup diagnostic — import the app, capture errors, serve results."""
import json
import os
import sys
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

port = int(os.environ.get("PORT", 8000))
result = {"port": port, "env_keys": sorted(os.environ.keys())}

# Step 1: Check DATABASE_URL exists
result["has_database_url"] = bool(os.environ.get("DATABASE_URL"))
result["environment"] = os.environ.get("ENVIRONMENT", "(not set)")

# Step 2: Try importing the app
try:
    print("Step 2: Importing app.config...", flush=True)
    from app.config import get_settings
    settings = get_settings()
    result["config_ok"] = True
    result["db_url_prefix"] = settings.database_url[:30] + "..." if settings.database_url else "(empty)"
except Exception:
    result["config_ok"] = False
    result["config_error"] = traceback.format_exc()
    print(f"Config import failed:\n{result['config_error']}", flush=True)

try:
    print("Step 3: Importing app.database...", flush=True)
    from app.database import get_pool
    result["database_module_ok"] = True
except Exception:
    result["database_module_ok"] = False
    result["database_module_error"] = traceback.format_exc()
    print(f"Database import failed:\n{result['database_module_error']}", flush=True)

try:
    print("Step 4: Importing routers...", flush=True)
    from app.routers import (
        actions, analytics, audit_report, auth, competitors,
        gamification, google_integration, ingestion, intelligence,
        og_image, retention, sites,
    )
    result["routers_ok"] = True
except Exception:
    result["routers_ok"] = False
    result["routers_error"] = traceback.format_exc()
    print(f"Router import failed:\n{result['routers_error']}", flush=True)

try:
    print("Step 5: Importing app.main...", flush=True)
    from app.main import app as fastapi_app
    result["app_ok"] = True
except Exception:
    result["app_ok"] = False
    result["app_error"] = traceback.format_exc()
    print(f"App import failed:\n{result['app_error']}", flush=True)

result_json = json.dumps(result, indent=2, default=str)
print(f"Diagnostic result:\n{result_json}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(result_json.encode())

    def log_message(self, format, *args):
        print(f"Request: {format % args}", flush=True)


print(f"Diagnostic server starting on port {port}...", flush=True)
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
