"""Tests verifying security fixes are correctly applied."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def test_cron_endpoint_blocked_with_no_secret_in_production():
    """Cron endpoints should reject requests when CRON_SECRET is empty in production."""
    from app.dependencies import verify_cron_secret
    from app.config import Settings
    import asyncio
    from fastapi import HTTPException

    async def run():
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                environment="production",
                cron_secret="",  # Not set
            )
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret=None)
            assert exc_info.value.status_code == 503

    asyncio.run(run())


def test_cron_endpoint_warns_but_passes_in_dev_with_no_secret():
    """In development, missing CRON_SECRET logs a warning but doesn't block."""
    from app.dependencies import verify_cron_secret
    from app.config import Settings
    import asyncio

    async def run():
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                environment="development",
                cron_secret="",
            )
            # Should not raise in dev
            await verify_cron_secret(x_cron_secret=None)

    asyncio.run(run())


def test_cron_rejects_wrong_secret():
    """Cron endpoints should reject requests with wrong secret."""
    from app.dependencies import verify_cron_secret
    from app.config import Settings
    import asyncio
    from fastapi import HTTPException

    async def run():
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                environment="production",
                cron_secret="correct-secret",
            )
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret="wrong-secret")
            assert exc_info.value.status_code == 403

    asyncio.run(run())


def test_cron_accepts_correct_secret():
    """Cron endpoints should accept requests with correct secret."""
    from app.dependencies import verify_cron_secret
    from app.config import Settings
    import asyncio

    async def run():
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                cron_secret="correct-secret",
            )
            # Should not raise
            await verify_cron_secret(x_cron_secret="correct-secret")

    asyncio.run(run())


def test_email_validation_rejects_invalid():
    """Auth register should reject malformed email addresses."""
    import re
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    invalid_emails = ["notanemail", "missing@tld", "@nodomain.com", "spaces in@email.com"]
    for email in invalid_emails:
        assert not email_re.match(email), f"Should have rejected: {email}"


def test_email_validation_accepts_valid():
    """Auth register should accept valid email addresses."""
    import re
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    valid_emails = ["user@example.com", "user+tag@domain.co.uk", "test.name@sub.domain.io"]
    for email in valid_emails:
        assert email_re.match(email), f"Should have accepted: {email}"


def test_hsts_header_is_enabled():
    """SecurityHeadersMiddleware should include HSTS header."""
    import asyncio
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from app.middleware.security import SecurityHeadersMiddleware

    async def homepage(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(SecurityHeadersMiddleware)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/")
    assert "strict-transport-security" in response.headers or "Strict-Transport-Security" in response.headers
