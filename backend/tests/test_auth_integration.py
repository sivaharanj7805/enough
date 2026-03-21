"""Integration tests for auth endpoints (/v1/auth/*)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import TEST_USER_ID, TEST_SITE_ID, MockConnection, make_record

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}


def _make_pool_mock(conn):
    """Create a pool mock that works with `async with pool.acquire() as db:`."""
    pool_obj = MagicMock()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=None)
    pool_obj.acquire.return_value = acm
    return pool_obj


@pytest.fixture
def mock_conn():
    return MockConnection()


@pytest.fixture
def app_with_mocks(mock_conn):
    """Create app with mocked database via dependency_overrides."""
    from app.config import get_settings
    get_settings.cache_clear()

    pool_obj = _make_pool_mock(mock_conn)

    with patch("app.database.get_pool") as mock_pool:
        async def _mock_get_pool():
            return pool_obj
        mock_pool.side_effect = _mock_get_pool

        from importlib import reload
        import app.main
        reload(app.main)
        the_app = app.main.app

        # Override the get_db dependency so FastAPI resolves it correctly
        from app.database import get_db
        async def _override_get_db():
            yield mock_conn
        the_app.dependency_overrides[get_db] = _override_get_db

        yield the_app, mock_conn

        the_app.dependency_overrides.clear()


# ── Registration ──


@pytest.mark.asyncio
async def test_register_success(app_with_mocks):
    app, conn = app_with_mocks

    mock_user = MagicMock()
    mock_user.id = TEST_USER_ID
    mock_session = MagicMock()
    mock_session.access_token = "access-token-123"
    mock_session.refresh_token = "refresh-token-456"
    mock_result = MagicMock()
    mock_result.user = mock_user
    mock_result.session = mock_session

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.sign_up.return_value = mock_result
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/register", json={
                "email": "test@example.com",
                "password": "SecurePass123!",
                "full_name": "Test User",
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "access-token-123"
    assert data["user_id"] == TEST_USER_ID
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_register_invalid_email(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass123!",
        })

    assert resp.status_code == 422
    assert "Invalid email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_email_confirmation_required(app_with_mocks):
    """When Supabase requires email confirmation, session is None."""
    app, conn = app_with_mocks

    mock_user = MagicMock()
    mock_user.id = TEST_USER_ID
    mock_result = MagicMock()
    mock_result.user = mock_user
    mock_result.session = None

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.sign_up.return_value = mock_result
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/register", json={
                "email": "test@example.com",
                "password": "SecurePass123!",
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == ""
    assert data["user_id"] == TEST_USER_ID


# ── Login ──


@pytest.mark.asyncio
async def test_login_success(app_with_mocks):
    app, *_ = app_with_mocks

    mock_user = MagicMock()
    mock_user.id = TEST_USER_ID
    mock_session = MagicMock()
    mock_session.access_token = "access-tok"
    mock_session.refresh_token = "refresh-tok"
    mock_result = MagicMock()
    mock_result.user = mock_user
    mock_result.session = mock_session

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.return_value = mock_result
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/login", json={
                "email": "test@example.com",
                "password": "correct-password",
            })

    assert resp.status_code == 200
    assert resp.json()["access_token"] == "access-tok"


@pytest.mark.asyncio
async def test_login_wrong_password(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/login", json={
                "email": "test@example.com",
                "password": "wrong-password",
            })

    assert resp.status_code == 401
    assert "Invalid credentials" in resp.json()["detail"]


# ── Magic Link ──


@pytest.mark.asyncio
async def test_magic_link_success(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_otp.return_value = None
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/magic-link", json={
                "email": "test@example.com",
                "password": "ignored",
            })

    assert resp.status_code == 200
    assert "Magic link sent" in resp.json()["message"]


# ── Google OAuth ──


@pytest.mark.asyncio
async def test_google_oauth_redirect(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/v1/auth/google")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "accounts.google.com" in location
    assert "response_type=code" in location
    assert "scope=" in location


@pytest.mark.asyncio
async def test_google_oauth_redirect_with_site_id(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get(f"/v1/auth/google?site_id={TEST_SITE_ID}")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "state=" in location


@pytest.mark.asyncio
async def test_google_callback_token_exchange_failure(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.httpx.AsyncClient") as mock_httpx:
        import httpx as _httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=MagicMock(text="invalid code")
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(return_value=mock_response)))
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/v1/auth/google/callback?code=bad-code&state=test")

    assert resp.status_code == 400


# ── Password Reset ──


@pytest.mark.asyncio
async def test_password_reset_returns_generic_message(app_with_mocks):
    """Password reset should always return the same message to prevent email enumeration."""
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.reset_password_email.return_value = None
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/password-reset", json={
                "email": "test@example.com",
            })

    assert resp.status_code == 200
    assert "If an account exists" in resp.json()["message"]


@pytest.mark.asyncio
async def test_password_reset_invalid_email_still_generic(app_with_mocks):
    """Even with invalid email format, return 422 (not enumeration leak)."""
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/password-reset", json={
            "email": "not-valid",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_password_reset_confirm_success(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.set_session.return_value = None
        mock_client.auth.update_user.return_value = None
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/password-reset/confirm", json={
                "access_token": "valid-token-from-email",
                "new_password": "NewSecurePass123!",
            })

    assert resp.status_code == 200
    assert "Password updated" in resp.json()["message"]


@pytest.mark.asyncio
async def test_password_reset_confirm_expired_token(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.set_session.side_effect = Exception("Token expired")
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/password-reset/confirm", json={
                "access_token": "expired-token",
                "new_password": "NewPass123!",
            })

    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


# ── Resend Verification ──


@pytest.mark.asyncio
async def test_resend_verification_success(app_with_mocks):
    app, *_ = app_with_mocks

    with patch("app.routers.auth.get_supabase_client") as mock_sb:
        mock_client = MagicMock()
        mock_client.auth.resend.return_value = None
        mock_sb.return_value = mock_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/auth/resend-verification", json={
                "email": "test@example.com",
            })

    assert resp.status_code == 200
    assert "Verification email sent" in resp.json()["message"]


@pytest.mark.asyncio
async def test_resend_verification_bad_email(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/resend-verification", json={
            "email": "bad",
        })

    assert resp.status_code == 422


# ── Account Deletion ──


@pytest.mark.asyncio
async def test_delete_account_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.auth.get_supabase_admin") as mock_admin:
        mock_admin_client = MagicMock()
        mock_admin_client.auth.admin.delete_user.return_value = None
        mock_admin.return_value = mock_admin_client

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete("/v1/auth/account", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_account_no_auth(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete("/v1/auth/account")

    assert resp.status_code == 422  # Missing Authorization header


# ── Terms Acceptance ──


@pytest.mark.asyncio
async def test_accept_terms_success(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/accept-terms", json={"accepted": True}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "accepted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_accept_terms_rejected(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/accept-terms", json={"accepted": False}, headers=AUTH_HEADER)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_accept_terms_no_auth(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/auth/accept-terms", json={"accepted": True})

    assert resp.status_code == 422
