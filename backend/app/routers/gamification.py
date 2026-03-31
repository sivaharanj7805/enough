"""Gamification endpoints — streaks, content wrapped, ecosystem forecasts."""

import logging
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────── Helpers ────────────────────


async def _verify_site(site_id: UUID, user_id: str, db: asyncpg.Connection) -> None:
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


# ──────────────────── Streaks ────────────────────


@router.get("/sites/{site_id}/gamification/streaks")
async def get_streaks(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get current streak data for user on a site."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        """SELECT current_streak, longest_streak, last_check_in, total_check_ins, created_at
           FROM user_streaks WHERE user_id = $1 AND site_id = $2""",
        user_id, site_id,
    )

    if not row:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "last_check_in": None,
            "total_check_ins": 0,
            "milestone": None,
        }

    current = row["current_streak"]
    milestone = None
    if current >= 100:
        milestone = "gold"
    elif current >= 30:
        milestone = "silver"
    elif current >= 7:
        milestone = "bronze"

    return {
        "current_streak": current,
        "longest_streak": row["longest_streak"],
        "last_check_in": str(row["last_check_in"]) if row["last_check_in"] else None,
        "total_check_ins": row["total_check_ins"],
        "milestone": milestone,
    }


@router.post("/sites/{site_id}/gamification/streaks/check-in")
async def daily_check_in(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Record a daily check-in and update streak."""
    await _verify_site(site_id, user_id, db)

    today = date.today()

    row = await db.fetchrow(
        "SELECT * FROM user_streaks WHERE user_id = $1 AND site_id = $2",
        user_id, site_id,
    )

    if not row:
        # First check-in ever
        await db.execute(
            """INSERT INTO user_streaks (user_id, site_id, current_streak, longest_streak, last_check_in, total_check_ins)
               VALUES ($1, $2, 1, 1, $3, 1)""",
            user_id, site_id, today,
        )
        return {
            "current_streak": 1,
            "longest_streak": 1,
            "last_check_in": str(today),
            "total_check_ins": 1,
            "milestone": None,
            "message": "First check-in! Your streak has begun.",
        }

    last_check_in = row["last_check_in"]

    if last_check_in == today:
        # Already checked in today
        current = row["current_streak"]
        milestone = None
        if current >= 100:
            milestone = "gold"
        elif current >= 30:
            milestone = "silver"
        elif current >= 7:
            milestone = "bronze"
        return {
            "current_streak": current,
            "longest_streak": row["longest_streak"],
            "last_check_in": str(today),
            "total_check_ins": row["total_check_ins"],
            "milestone": milestone,
            "message": "Already checked in today!",
        }

    # Calculate new streak
    days_diff = (today - last_check_in).days if last_check_in else 999

    if days_diff == 1:
        new_streak = row["current_streak"] + 1
    else:
        new_streak = 1  # Reset streak

    new_longest = max(row["longest_streak"], new_streak)
    new_total = row["total_check_ins"] + 1

    await db.execute(
        """UPDATE user_streaks
           SET current_streak = $1, longest_streak = $2, last_check_in = $3, total_check_ins = $4
           WHERE user_id = $5 AND site_id = $6""",
        new_streak, new_longest, today, new_total, user_id, site_id,
    )

    milestone = None
    if new_streak >= 100:
        milestone = "gold"
    elif new_streak >= 30:
        milestone = "silver"
    elif new_streak >= 7:
        milestone = "bronze"

    messages = {
        7: "Bronze milestone! 7-day streak!",
        30: "Silver milestone! 30-day streak!",
        100: "Gold milestone! 100-day streak!",
    }
    message = messages.get(new_streak, f"Day {new_streak} streak!")

    return {
        "current_streak": new_streak,
        "longest_streak": new_longest,
        "last_check_in": str(today),
        "total_check_ins": new_total,
        "milestone": milestone,
        "message": message,
    }


# ──────────────────── Content Wrapped ────────────────────


@router.get("/sites/{site_id}/gamification/wrapped/{period}")
async def get_wrapped(
    site_id: UUID,
    period: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get content wrapped data for a period (e.g. '2025-12' or '2025')."""
    await _verify_site(site_id, user_id, db)

    row = await db.fetchrow(
        "SELECT data, created_at FROM content_wrapped WHERE site_id = $1 AND period = $2",
        site_id, period,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Wrapped data not found for this period. Generate it first.")

    import json
    data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"])
    return {
        "period": period,
        "data": data,
        "generated_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.post("/sites/{site_id}/gamification/wrapped/generate")
async def generate_wrapped(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate wrapped data for the current or specified period."""
    await _verify_site(site_id, user_id, db)

    from app.services.content_wrapped import ContentWrappedService

    service = ContentWrappedService()

    # Determine period: current year for yearly, or last month for monthly
    today = date.today()
    period = str(today.year - 1) if today.month > 1 else f"{today.year - 1}-{today.month:02d}"

    result = await service.generate(db, site_id, period)

    return {
        "period": period,
        "data": result,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ──────────────────── Ecosystem Weather Forecast ────────────────────


@router.get("/sites/{site_id}/gamification/forecast")
async def get_forecast(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get 7-day content ecosystem weather forecast."""
    await _verify_site(site_id, user_id, db)

    from app.services.ecosystem_forecast import EcosystemForecastService

    service = EcosystemForecastService()
    forecast = await service.generate_forecast(db, site_id)

    return {
        "site_id": str(site_id),
        "forecast": forecast,
    }
