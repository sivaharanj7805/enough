"""Retention & Growth endpoints — reports, impact tracking, steward, billing."""

import logging
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.schemas import (
    ReportHistoryEntry,
    ImpactTrackingResponse,
    ImpactSnapshotResponse,
    ImpactDetailResponse,
    ImpactCardResponse,
    StartTrackingRequest,
    StewardProfile,
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionResponse,
    PortalResponse,
    TaskTriggerResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────── Helpers ────────────────────


async def _verify_site(site_id: UUID, user_id: str, db: asyncpg.Connection) -> None:
    """Ensure the user owns the site."""
    row = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")


# ──────────────────── Weekly Reports ────────────────────


@router.post("/reports/send-weekly", response_model=TaskTriggerResponse)
async def send_weekly_report(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Trigger weekly report for all user sites."""
    from app.services.weekly_report import WeeklyReportService

    service = WeeklyReportService()
    sites = await db.fetch("SELECT id FROM sites WHERE user_id = $1", user_id)

    sent = 0
    for site in sites:
        if await service.send_report(db, site["id"]):
            sent += 1

    return TaskTriggerResponse(
        message=f"Weekly reports sent for {sent}/{len(sites)} sites",
        site_id=sites[0]["id"] if sites else UUID(int=0),
    )


@router.get(
    "/sites/{site_id}/reports/history",
    response_model=list[ReportHistoryEntry],
)
async def get_report_history(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List past report history for a site."""
    await _verify_site(site_id, user_id, db)

    from app.services.weekly_report import WeeklyReportService

    service = WeeklyReportService()
    history = await service.get_history(db, site_id)
    return [ReportHistoryEntry(**h) for h in history]


# ──────────────────── Impact Tracking ────────────────────


@router.post(
    "/sites/{site_id}/impact/track",
    response_model=ImpactTrackingResponse,
)
async def start_impact_tracking(
    site_id: UUID,
    body: StartTrackingRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Start tracking a consolidation's impact."""
    await _verify_site(site_id, user_id, db)

    from app.services.impact_tracker import ImpactTracker

    tracker = ImpactTracker()
    tracking_id = await tracker.start_tracking(
        db, site_id, body.cluster_id, body.consolidated_urls, body.pillar_url
    )

    # Fetch the created record
    items = await tracker.get_all_for_site(db, site_id)
    for item in items:
        if item["id"] == tracking_id:
            return ImpactTrackingResponse(
                id=item["id"],
                site_id=item["site_id"],
                cluster_id=item["cluster_id"],
                pillar_url=item["pillar_url"],
                consolidated_urls=item["consolidated_urls"],
                baseline_traffic=item["baseline_traffic"],
                baseline_avg_position=float(item["baseline_avg_position"]) if item["baseline_avg_position"] else None,
                baseline_date=str(item["baseline_date"]),
                latest_traffic=item["latest_traffic"],
                latest_avg_position=float(item["latest_avg_position"]) if item["latest_avg_position"] else None,
                latest_check_date=str(item["latest_check_date"]) if item["latest_check_date"] else None,
                traffic_change_pct=item["traffic_change_pct"],
                status=item["status"],
                days_since=item["days_since"],
            )

    raise HTTPException(status_code=500, detail="Failed to create tracking")


@router.get(
    "/sites/{site_id}/impact",
    response_model=list[ImpactTrackingResponse],
)
async def list_impact_trackings(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """List all impact trackings for a site."""
    await _verify_site(site_id, user_id, db)

    from app.services.impact_tracker import ImpactTracker

    tracker = ImpactTracker()
    items = await tracker.get_all_for_site(db, site_id)

    return [
        ImpactTrackingResponse(
            id=item["id"],
            site_id=item["site_id"],
            cluster_id=item["cluster_id"],
            pillar_url=item["pillar_url"],
            consolidated_urls=item["consolidated_urls"],
            baseline_traffic=item["baseline_traffic"],
            baseline_avg_position=float(item["baseline_avg_position"]) if item["baseline_avg_position"] else None,
            baseline_date=str(item["baseline_date"]),
            latest_traffic=item["latest_traffic"],
            latest_avg_position=float(item["latest_avg_position"]) if item["latest_avg_position"] else None,
            latest_check_date=str(item["latest_check_date"]) if item["latest_check_date"] else None,
            traffic_change_pct=item["traffic_change_pct"],
            status=item["status"],
            days_since=item["days_since"],
        )
        for item in items
    ]


@router.get(
    "/sites/{site_id}/impact/{tracking_id}",
    response_model=ImpactDetailResponse,
)
async def get_impact_detail(
    site_id: UUID,
    tracking_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get detailed impact view with snapshots."""
    await _verify_site(site_id, user_id, db)

    from app.services.impact_tracker import ImpactTracker

    tracker = ImpactTracker()
    try:
        detail = await tracker.get_detail(db, tracking_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Tracking not found")

    t = detail["tracking"]
    return ImpactDetailResponse(
        tracking=ImpactTrackingResponse(
            id=t["id"],
            site_id=t["site_id"],
            cluster_id=t["cluster_id"],
            pillar_url=t["pillar_url"],
            consolidated_urls=t["consolidated_urls"],
            baseline_traffic=t["baseline_traffic"],
            baseline_avg_position=float(t["baseline_avg_position"]) if t["baseline_avg_position"] else None,
            baseline_date=str(t["baseline_date"]),
            latest_traffic=t["latest_traffic"],
            latest_avg_position=float(t["latest_avg_position"]) if t["latest_avg_position"] else None,
            latest_check_date=str(t["latest_check_date"]) if t["latest_check_date"] else None,
            traffic_change_pct=t["traffic_change_pct"],
            status=t["status"],
            days_since=t["days_since"],
        ),
        snapshots=[
            ImpactSnapshotResponse(
                snapshot_date=str(s["snapshot_date"]),
                traffic=s["traffic"],
                avg_position=float(s["avg_position"]) if s["avg_position"] else None,
                redirects_working=s["redirects_working"],
                milestone=s["milestone"],
            )
            for s in detail["snapshots"]
        ],
    )


@router.post(
    "/sites/{site_id}/impact/{tracking_id}/check",
)
async def check_impact(
    site_id: UUID,
    tracking_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Trigger an impact check (compare current vs baseline)."""
    await _verify_site(site_id, user_id, db)

    from app.services.impact_tracker import ImpactTracker

    tracker = ImpactTracker()
    try:
        result = await tracker.check_impact(db, tracking_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Tracking not found")

    return result


@router.get(
    "/sites/{site_id}/impact/{tracking_id}/card",
    response_model=ImpactCardResponse,
)
async def get_impact_card(
    site_id: UUID,
    tracking_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate a shareable impact card."""
    await _verify_site(site_id, user_id, db)

    from app.services.impact_tracker import ImpactTracker

    tracker = ImpactTracker()
    try:
        card = await tracker.generate_impact_card(db, tracking_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Tracking not found")

    return ImpactCardResponse(**card)


# ──────────────────── Steward Profile ────────────────────


@router.get("/profile/steward", response_model=StewardProfile)
async def get_steward_profile(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get the current user's steward profile."""
    from app.services.steward import StewardService

    service = StewardService()
    profile = await service.get_profile(db, user_id)
    return StewardProfile(**profile)


# ──────────────────── Stripe Billing ────────────────────


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Create a Stripe checkout session."""
    from app.services.stripe_service import StripeService

    service = StripeService()
    try:
        url = await service.create_checkout_session(
            db, user_id, body.price_id, body.success_url, body.cancel_url
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Checkout creation failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkout")

    return CheckoutResponse(checkout_url=url)


@router.get("/billing/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get current subscription details."""
    from app.services.stripe_service import StripeService

    service = StripeService()
    sub = await service.get_subscription(db, user_id)
    return SubscriptionResponse(**sub)


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook handler — NO AUTH required (called by Stripe)."""
    from app.database import get_pool
    from app.services.stripe_service import StripeService

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    pool = await get_pool()
    async with pool.acquire() as db:
        service = StripeService()
        try:
            await service.handle_webhook(db, payload, sig_header)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Webhook processing failed: %s", e)
            raise HTTPException(status_code=500, detail="Webhook failed")

    return {"received": True}


@router.get("/billing/portal", response_model=PortalResponse)
async def get_billing_portal(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Get Stripe customer portal URL."""
    from app.services.stripe_service import StripeService

    service = StripeService()
    try:
        url = await service.get_portal_url(
            db, user_id, return_url="http://localhost:3000/billing"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PortalResponse(portal_url=url)
