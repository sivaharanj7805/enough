"""Tests for API v1 versioning — routes are under /v1/ prefix."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient


def _make_mock_pool():
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=1)
    mock_pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_pool.acquire = acquire
    return mock_pool


class TestAPIVersioning:
    """Verify routes are correctly under /v1/ prefix."""

    def _get_client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_health_at_root(self):
        """Health endpoint should be at / not /v1/."""
        async def fake_pool():
            return _make_mock_pool()

        with patch("app.main.get_pool", side_effect=fake_pool):
            client = self._get_client()
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_sites_under_v1(self):
        """Site routes should be under /v1/sites/."""
        client = self._get_client()
        # Without auth header → 422 (missing header), not 404
        resp = client.get("/v1/sites")
        assert resp.status_code != 404

    def test_old_routes_not_found(self):
        """Old un-versioned routes should 404."""
        client = self._get_client()
        resp = client.get("/sites")
        assert resp.status_code == 404

    def test_route_listing_has_v1(self):
        """All non-health routes should have /v1/ prefix."""
        from app.main import app
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        non_special = [
            r for r in routes
            if r not in ('/health', '/', '/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc')
        ]
        for route in non_special:
            assert route.startswith('/v1/'), f"Route {route} is not under /v1/"
