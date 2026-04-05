"""Security middleware for the Tended backend.

Provides:
- Security headers (HSTS, X-Frame-Options, CSP, etc.)
- Request size limiting
- Host header validation
- Request ID injection for tracing
"""

import logging
import secrets
import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Max request body size: 10MB
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID for tracing
        request_id = secrets.token_hex(8)
        request.state.request_id = request_id

        # Timing
        start = time.monotonic()

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000

        # ── Security Headers ──

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Don't send referrer to third parties
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict permissions/features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )

        # HSTS — enabled; reverse proxy / load balancer should handle TLS termination
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy (API returns JSON, no HTML rendering)
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # Request ID for tracing
        response.headers["X-Request-Id"] = request_id

        # Timing (useful for performance debugging)
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        # Don't reveal server info
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies larger than the configured limit."""

    def __init__(self, app, max_bytes: int = MAX_REQUEST_BODY_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check Content-Length header first (fast path)
        content_length = request.headers.get("content-length")

        try:
            content_length_int = int(content_length) if content_length else 0
        except (ValueError, TypeError):
            content_length_int = 0

        if content_length_int > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large. Max: {self.max_bytes // (1024*1024)}MB",
                },
            )

        # For chunked transfers without Content-Length, read and measure body
        if not content_length and request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Max: {self.max_bytes // (1024*1024)}MB",
                    },
                )

        return await call_next(request)


class HostValidationMiddleware(BaseHTTPMiddleware):
    """Validate the Host header to prevent host header injection attacks."""

    def __init__(self, app, allowed_hosts: list[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = set(h.lower() for h in (allowed_hosts or []))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.allowed_hosts:
            # No restriction configured — allow all
            return await call_next(request)

        # Skip host validation for health checks (Railway/Docker internal requests)
        if request.url.path == "/health":
            return await call_next(request)

        host = request.headers.get("host", "").split(":")[0].lower()

        if host not in self.allowed_hosts and host != "localhost" and host != "127.0.0.1":
            logger.warning("Rejected request with invalid Host header: %s", host)
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Host header"},
            )

        return await call_next(request)
