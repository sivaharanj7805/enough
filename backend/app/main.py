"""Enough — Content Ecosystem Intelligence Platform (Phase 1)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import get_pool, close_pool
from app.routers import auth, sites, ingestion, analytics

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
    logger.info("Starting Enough backend...")
    await get_pool()
    logger.info("Database pool ready")
    yield
    await close_pool()
    logger.info("Enough backend shutdown complete")


app = FastAPI(
    title="Enough",
    description="Content Ecosystem Intelligence Platform — Phase 1 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(sites.router, prefix="/sites", tags=["Sites"])
app.include_router(ingestion.router, prefix="/sites", tags=["Ingestion"])
app.include_router(analytics.router, prefix="/sites", tags=["Analytics"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "enough-backend", "version": "0.1.0"}
