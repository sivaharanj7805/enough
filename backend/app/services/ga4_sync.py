"""Google Analytics 4 data sync service."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg
import httpx

from app.services.google_auth import get_valid_token

logger = logging.getLogger(__name__)

GA4_API = "https://analyticsdata.googleapis.com/v1beta"


class GA4SyncService:
    """Sync GA4 metrics into ga4_metrics table."""

    async def list_ga4_properties(self, access_token: str) -> list[dict]:
        """List GA4 properties accessible to this account."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            properties = []
            for account in data.get("accountSummaries", []):
                for prop in account.get("propertySummaries", []):
                    properties.append({
                        "property_id": prop["property"].replace("properties/", ""),
                        "display_name": prop.get("displayName", ""),
                        "account": account.get("displayName", ""),
                    })
            return properties

    async def run_report(
        self,
        access_token: str,
        property_id: str,
        start_date: date,
        end_date: date,
        dimensions: list[str],
        metrics: list[str],
        limit: int = 10000,
    ) -> list[dict]:
        """Run a GA4 report."""
        payload = {
            "dateRanges": [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "keepEmptyRows": False,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GA4_API}/properties/{property_id}:runReport",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            if resp.status_code == 403:
                logger.warning("GA4 403 for property %s", property_id)
                return []
            resp.raise_for_status()
            data = resp.json()

        dimension_headers = [d["name"] for d in data.get("dimensionHeaders", [])]
        metric_headers = [m["name"] for m in data.get("metricHeaders", [])]

        rows = []
        for row in data.get("rows", []):
            row_dict = {}
            for i, val in enumerate(row.get("dimensionValues", [])):
                if i < len(dimension_headers):
                    row_dict[dimension_headers[i]] = val["value"]
            for i, val in enumerate(row.get("metricValues", [])):
                if i < len(metric_headers):
                    row_dict[metric_headers[i]] = val["value"]
            rows.append(row_dict)
        return rows

    async def sync_site(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        user_id: str,
        days_back: int = 90,
    ) -> dict:
        """Full GA4 sync for a site."""
        access_token = await get_valid_token(db, site_id, user_id)
        if not access_token:
            return {"error": "No Google token — connect Google account first", "synced": 0}

        row = await db.fetchrow(
            "SELECT ga4_property_id, domain FROM sites WHERE id = $1", site_id,
        )
        if not row:
            return {"error": "Site not found", "synced": 0}

        property_id = row["ga4_property_id"]
        if not property_id:
            # Try to auto-detect
            try:
                properties = await self.list_ga4_properties(access_token)
                domain = (row["domain"] or "").replace("www.", "")
                for prop in properties:
                    if domain and domain in prop["display_name"].lower():
                        property_id = prop["property_id"]
                        await db.execute(
                            "UPDATE sites SET ga4_property_id = $1 WHERE id = $2",
                            property_id, site_id,
                        )
                        break
            except Exception as e:
                logger.error("Could not list GA4 properties: %s", e)

        if not property_id:
            return {"error": "No GA4 property ID configured — set it in site settings", "synced": 0}

        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days_back)

        logger.info("Syncing GA4 for site %s (property %s)", site_id, property_id)

        try:
            rows = await self.run_report(
                access_token=access_token,
                property_id=property_id,
                start_date=start_date,
                end_date=end_date,
                dimensions=["pagePath", "date"],
                metrics=[
                    "screenPageViews",
                    "sessions",
                    "bounceRate",
                    "averageSessionDuration",
                    "engagedSessions",
                ],
                limit=25000,
            )
        except Exception as e:
            logger.error("GA4 API error for site %s: %s", site_id, e)
            return {"error": str(e), "synced": 0}

        if not rows:
            return {"synced": 0, "message": "No GA4 data returned"}

        # Get all post URLs for this site
        post_rows = await db.fetch(
            "SELECT id, url FROM posts WHERE site_id = $1", site_id,
        )
        path_to_post_id: dict[str, UUID] = {}
        for p in post_rows:
            try:
                from urllib.parse import urlparse
                path = urlparse(p["url"]).path.rstrip("/").lower()
                path_to_post_id[path] = p["id"]
            except Exception:
                logger.warning("Failed to parse URL for post %s", p["id"])

        synced = 0
        for row in rows:
            page_path = row.get("pagePath", "").rstrip("/").lower()
            row_date_str = row.get("date", "")
            if not row_date_str or len(row_date_str) != 8:
                continue

            row_date = date(int(row_date_str[:4]), int(row_date_str[4:6]), int(row_date_str[6:]))
            post_id = path_to_post_id.get(page_path)
            if not post_id:
                continue

            pageviews = int(row.get("screenPageViews", 0) or 0)
            sessions = int(row.get("sessions", 0) or 0)
            bounce_rate = float(row.get("bounceRate", 0) or 0)
            avg_duration = float(row.get("averageSessionDuration", 0) or 0)
            engaged = int(row.get("engagedSessions", 0) or 0)

            await db.execute("""
                INSERT INTO ga4_metrics
                    (post_id, date, pageviews, sessions, bounce_rate,
                     avg_session_duration, engaged_sessions)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (post_id, date) DO UPDATE SET
                    pageviews = EXCLUDED.pageviews,
                    sessions = EXCLUDED.sessions,
                    bounce_rate = EXCLUDED.bounce_rate,
                    avg_session_duration = EXCLUDED.avg_session_duration,
                    engaged_sessions = EXCLUDED.engaged_sessions,
                    updated_at = NOW()
            """,
                post_id, row_date,
                pageviews, sessions, bounce_rate, avg_duration, engaged,
            )
            synced += 1

        await db.execute(
            "UPDATE sites SET last_ga4_sync = NOW() WHERE id = $1", site_id,
        )

        logger.info("GA4 sync complete for site %s: %d rows synced", site_id, synced)
        return {
            "synced": synced,
            "date_range": f"{start_date} to {end_date}",
            "property_id": property_id,
        }
