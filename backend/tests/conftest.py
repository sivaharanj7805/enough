"""Shared fixtures for the Tended backend test suite."""

import os
import sys
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Patch settings before any app import ──
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
os.environ.setdefault("RESEND_API_KEY", "re_test_fake")


# ── Common IDs ──
TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_SITE_ID = UUID("11111111-2222-3333-4444-555555555555")
TEST_CLUSTER_ID = UUID("22222222-3333-4444-5555-666666666666")
TEST_POST_ID_A = UUID("33333333-4444-5555-6666-777777777777")
TEST_POST_ID_B = UUID("44444444-5555-6666-7777-888888888888")
TEST_POST_ID_C = UUID("55555555-6666-7777-8888-999999999999")
TEST_TRACKING_ID = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")


@pytest.fixture
def user_id():
    return TEST_USER_ID


@pytest.fixture
def site_id():
    return TEST_SITE_ID


@pytest.fixture
def cluster_id():
    return TEST_CLUSTER_ID


# ── Mock DB Connection ──

class MockRecord(dict):
    """Simulates asyncpg.Record — dict with attribute access."""
    def __getitem__(self, key):
        return super().__getitem__(key)


def make_record(**kwargs) -> MockRecord:
    return MockRecord(**kwargs)


class MockConnection:
    """Minimal asyncpg.Connection mock for unit tests."""

    def __init__(self):
        self._fetchval_returns = []
        self._fetchrow_returns = []
        self._fetch_returns = []
        self._execute_results = []

    async def fetch(self, query, *args):
        if self._fetch_returns:
            return self._fetch_returns.pop(0)
        return []

    async def fetchrow(self, query, *args):
        if self._fetchrow_returns:
            return self._fetchrow_returns.pop(0)
        return None

    async def fetchval(self, query, *args):
        if self._fetchval_returns:
            return self._fetchval_returns.pop(0)
        return None

    async def execute(self, query, *args):
        if self._execute_results:
            return self._execute_results.pop(0)
        return "OK"

    async def executemany(self, query, args_list):
        return None


@pytest.fixture
def mock_db():
    """Provide a MockConnection for tests that need DB."""
    return MockConnection()


# ── FastAPI Test Client ──

@pytest.fixture
def mock_pool():
    """Mock the database pool."""
    pool = AsyncMock()
    conn = MockConnection()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ── Sample Data Factories ──

@pytest.fixture
def sample_post_rows():
    """Generate sample post rows for health scoring tests."""
    now = datetime.now(timezone.utc)
    return [
        make_record(
            id=TEST_POST_ID_A,
            title="Best Python Frameworks 2024",
            url="/python-frameworks",
            publish_date=now - timedelta(days=60),
            word_count=2500,
        ),
        make_record(
            id=TEST_POST_ID_B,
            title="Django vs Flask Comparison",
            url="/django-vs-flask",
            publish_date=now - timedelta(days=30),
            word_count=1800,
        ),
        make_record(
            id=TEST_POST_ID_C,
            title="Getting Started with FastAPI",
            url="/fastapi-tutorial",
            publish_date=now - timedelta(days=5),
            word_count=1200,
        ),
    ]
