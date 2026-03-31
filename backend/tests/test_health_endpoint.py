"""Tests for the /health endpoint."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient


def _make_mock_pool(fetchval_return=1):
    """Create a properly structured async mock pool."""
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=fetchval_return)

    mock_pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield mock_conn

    mock_pool.acquire = acquire
    return mock_pool


class TestHealthEndpoint:
    """Test the root /health endpoint."""

    def test_health_returns_ok(self):
        """Health check should return 200 with status ok when DB is connected."""
        mock_pool = _make_mock_pool(fetchval_return=1)

        async def fake_get_pool():
            return mock_pool

        with patch("app.main.get_pool", side_effect=fake_get_pool):
            from app.main import app
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert data["service"] == "tended-backend"

    def test_health_not_under_v1(self):
        """Health endpoint should NOT be behind /v1/ prefix."""
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/v1/health")
        assert response.status_code == 404 or response.status_code == 405
