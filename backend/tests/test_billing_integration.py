"""Integration tests for billing/Stripe endpoints (/v1/billing/*)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import TEST_USER_ID, MockConnection

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}


def _make_pool_mock(conn):
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

        from app.database import get_db
        async def _override_get_db():
            yield mock_conn
        the_app.dependency_overrides[get_db] = _override_get_db

        yield the_app, mock_conn

        the_app.dependency_overrides.clear()


# ── Checkout ──


@pytest.mark.asyncio
async def test_create_checkout_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.create_checkout_session = AsyncMock(return_value="https://checkout.stripe.com/session123")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/billing/checkout", json={
                "price_id": "price_growth_monthly",
                "success_url": "https://app.enough.io/success",
                "cancel_url": "https://app.enough.io/cancel",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/session123"


@pytest.mark.asyncio
async def test_create_checkout_invalid_price(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.create_checkout_session = AsyncMock(side_effect=ValueError("Invalid price_id"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/billing/checkout", json={
                "price_id": "price_invalid",
                "success_url": "https://app.enough.io/success",
                "cancel_url": "https://app.enough.io/cancel",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 400
    assert "Invalid price_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_checkout_no_auth(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/billing/checkout", json={
            "price_id": "price_growth_monthly",
            "success_url": "https://app.enough.io/success",
            "cancel_url": "https://app.enough.io/cancel",
        })

    assert resp.status_code == 422


# ── Subscription ──


@pytest.mark.asyncio
async def test_get_subscription_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.get_subscription = AsyncMock(return_value={
            "tier": "growth",
            "status": "active",
            "stripe_subscription_id": "sub_abc123",
            "current_period_end": "2026-04-01T00:00:00Z",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/v1/billing/subscription", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "growth"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_get_subscription_no_auth(app_with_mocks):
    app, *_ = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/billing/subscription")

    assert resp.status_code == 422


# ── Webhook ──


@pytest.mark.asyncio
async def test_stripe_webhook_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.handle_webhook = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "t=123,v1=abc"},
            )

    assert resp.status_code == 200
    assert resp.json()["received"] is True


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.handle_webhook = AsyncMock(side_effect=ValueError("Invalid signature"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "invalid"},
            )

    assert resp.status_code == 400
    assert "Invalid signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_stripe_webhook_processing_error(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.handle_webhook = AsyncMock(side_effect=RuntimeError("DB error"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/billing/webhook",
                content=b'{"type": "invoice.paid"}',
                headers={"stripe-signature": "t=123,v1=abc"},
            )

    assert resp.status_code == 500


# ── Portal ──


@pytest.mark.asyncio
async def test_get_billing_portal_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.get_portal_url = AsyncMock(return_value="https://billing.stripe.com/portal/sess_abc")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/v1/billing/portal", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "stripe.com" in resp.json()["portal_url"]


@pytest.mark.asyncio
async def test_get_billing_portal_no_customer(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.get_portal_url = AsyncMock(side_effect=ValueError("No Stripe customer found"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/v1/billing/portal", headers=AUTH_HEADER)

    assert resp.status_code == 400
