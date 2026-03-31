"""Tended — Content Ecosystem Intelligence Platform (Phase 1)."""

import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Initialise Sentry before anything else
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FastApiIntegration(), AsyncioIntegration()],
        traces_sample_rate=0.1,
        environment=os.environ.get("ENVIRONMENT", "production"),
        send_default_pii=False,
    )

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, validate_production
from app.database import close_pool, get_pool
from app.routers import (
    actions,
    analytics,
    audit_report,
    auth,
    competitors,
    gamification,
    google_integration,
    ingestion,
    intelligence,
    og_image,
    retention,
    sites,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    import asyncio

    logger.info("Starting Tended backend...")
    # Validate production configuration at startup — fail fast if misconfigured
    validate_production()
    pool = await get_pool()
    logger.info("Database pool ready")

    # Start the job queue worker — processes crawl/pipeline jobs from Postgres.
    # Survives process restarts (jobs stay in DB), unlike BackgroundTasks.
    from app.services.job_queue import run_worker
    worker_task = asyncio.create_task(run_worker(pool))

    yield

    # Graceful shutdown: cancel the worker, then close the pool
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await close_pool()
    logger.info("Tended backend shutdown complete")


_is_production = os.environ.get("ENVIRONMENT", "production") == "production"

app = FastAPI(
    title="Tended",
    description="Content Ecosystem Intelligence Platform — Phase 1 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)

# ── Security Middleware (order matters — outermost first) ──
settings = get_settings()

from app.middleware.security import (
    HostValidationMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

# Security headers on every response
app.add_middleware(SecurityHeadersMiddleware)

# Request size limit (10MB)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)

# Host header validation (if configured)
if settings.allowed_host_list:
    app.add_middleware(HostValidationMiddleware, allowed_hosts=settings.allowed_host_list)

# CORS (must be added after other middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Cron-Secret", "X-Request-Id"],
    expose_headers=["X-Request-Id", "X-Response-Time"],
    max_age=86400,
)

# ── API Rate Limiting (slowapi) ──
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── v1 API Router ──
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
v1_router.include_router(sites.router, prefix="/sites", tags=["Sites"])
v1_router.include_router(ingestion.router, prefix="/sites", tags=["Ingestion"])
v1_router.include_router(analytics.router, prefix="/sites", tags=["Analytics"])
v1_router.include_router(intelligence.router, prefix="/sites", tags=["Intelligence"])
v1_router.include_router(actions.router, prefix="/sites", tags=["Actions"])
v1_router.include_router(retention.router, tags=["Retention"])
v1_router.include_router(google_integration.router, tags=["Google"])
v1_router.include_router(audit_report.router, prefix="/sites", tags=["Audit"])
v1_router.include_router(og_image.router, prefix="/sites", tags=["OG"])
v1_router.include_router(gamification.router, tags=["Gamification"])
v1_router.include_router(competitors.router, prefix="/sites", tags=["Competitors"])

from app.routers import prospects, unsubscribe

v1_router.include_router(prospects.router, tags=["Prospects"])
v1_router.include_router(unsubscribe.router, tags=["Unsubscribe"])

app.include_router(v1_router)


@app.get("/health")
async def health_check():
    """Health check endpoint — verifies DB connectivity."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result != 1:
                raise Exception("Unexpected DB response")
        return {
            "status": "ok",
            "service": "tended-backend",
            "version": "0.1.0",
            "database": "connected",
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": "tended-backend",
                "version": "0.1.0",
                "database": "disconnected",
                # Do not expose internal error details to clients
            },
        )
