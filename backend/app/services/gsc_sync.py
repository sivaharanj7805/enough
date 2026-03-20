"""Google Search Console data sync service."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg
import httpx

from app.services.google_auth import get_valid_token

logger = logging.getLogger(__name__)

GSC_API = "https://searchconsole.googleapis.com/webmasters/v3"


class GSCSyncService:
    """Sync GSC search analytics into gsc_metrics table."""

    async def list_gsc_sites(self, access_token: str) -> list[str]:
        """List all GSC-verified sites for this account."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GSC_API}/sites",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return [s["siteUrl"] for s in data.get("siteEntry", [])]

    async def fetch_search_analytics(
        self,
        access_token: str,
        site_url: str,
        start_date: date,
        end_date: date,
        dimensions: list[str] | None = None,
        row_limit: int = 5000,
    ) -> list[dict]:
        """Fetch search analytics data from GSC."""
        if dimensions is None:
            dimensions = ["page", "query"]

        payload = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "dataState": "final",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GSC_API}/sites/{site_url}/searchAnalytics/query",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            if resp.status_code == 403:
                logger.warning("GSC 403 for %s — site may not be verified", site_url)
                return []
            resp.raise_for_status()
            return resp.json().get("rows", [])

    async def sync_site(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        user_id: str,
        days_back: int = 90,
    ) -> dict:
        """Full GSC sync for a site — fetches last N days of search analytics."""
        access_token = await get_valid_token(db, site_id, user_id)
        if not access_token:
            return {"error": "No Google token — connect Google account first", "synced": 0}

        # Get the GSC site URL stored for this site
        row = await db.fetchrow(
            "SELECT gsc_site_url, domain FROM sites WHERE id = $1",
            site_id,
        )
        if not row:
            return {"error": "Site not found", "synced": 0}

        gsc_site_url = row["gsc_site_url"]
        if not gsc_site_url:
            # Try to find it from verified sites
            try:
                verified = await self.list_gsc_sites(access_token)
                domain = row["domain"] or ""
                for vurl in verified:
                    if domain in vurl or vurl in domain:
                        gsc_site_url = vurl
                        await db.execute(
                            "UPDATE sites SET gsc_site_url = $1 WHERE id = $2",
                            gsc_site_url, site_id,
                        )
                        break
            except Exception as e:
                logger.error("Could not list GSC sites: %s", e)

        if not gsc_site_url:
            return {"error": "No GSC site URL configured — set it in site settings", "synced": 0}

        end_date = date.today() - timedelta(days=3)  # GSC has ~3 day lag
        start_date = end_date - timedelta(days=days_back)

        logger.info("Syncing GSC for site %s (%s) from %s to %s", site_id, gsc_site_url, start_date, end_date)

        try:
            rows = await self.fetch_search_analytics(
                access_token, gsc_site_url, start_date, end_date,
                dimensions=["page", "query", "date"],
                row_limit=25000,
            )
        except Exception as e:
            logger.error("GSC API error for site %s: %s", site_id, e)
            return {"error": str(e), "synced": 0}

        if not rows:
            return {"synced": 0, "message": "No GSC data returned — site may have no search traffic yet"}

        # Get all post URLs for this site
        post_rows = await db.fetch(
            "SELECT id, url FROM posts WHERE site_id = $1", site_id,
        )
        url_to_post_id = {}
        for p in post_rows:
            normalized = p["url"].rstrip("/").lower()
            url_to_post_id[normalized] = p["id"]

        def normalize_url(url: str) -> str:
            return url.rstrip("/").lower()

        # Aggregate by (page, date)
        page_date_agg: dict[tuple, dict] = {}
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 3:
                continue
            page_url, query, row_date = keys[0], keys[1], keys[2]
            norm_page = normalize_url(page_url)
            key = (norm_page, row_date)
            if key not in page_date_agg:
                page_date_agg[key] = {
                    "clicks": 0, "impressions": 0, "ctr_sum": 0.0,
                    "position_sum": 0.0, "query_count": 0,
                    "top_queries": {},
                }
            agg = page_date_agg[key]
            row_impressions = row.get("impressions", 0)
            agg["clicks"] += row.get("clicks", 0)
            agg["impressions"] += row_impressions
            agg["ctr_sum"] += row.get("ctr", 0.0) * row_impressions
            agg["position_sum"] += row.get("position", 0.0) * row_impressions
            agg["query_count"] += 1
            # Track top queries by clicks
            q_clicks = row.get("clicks", 0)
            if q_clicks > 0:
                agg["top_queries"][query] = agg["top_queries"].get(query, 0) + q_clicks

        import json as _json
        synced = 0
        for (norm_page, row_date), agg in page_date_agg.items():
            post_id = url_to_post_id.get(norm_page)
            if not post_id:
                continue

            qcount = agg["query_count"]
            total_imp = agg["impressions"]
            avg_ctr = agg["ctr_sum"] / total_imp if total_imp else 0.0
            avg_pos = agg["position_sum"] / total_imp if total_imp else 0.0
            top_queries = sorted(
                agg["top_queries"].items(), key=lambda x: -x[1]
            )[:10]
            top_queries_json = _json.dumps([q for q, _ in top_queries])

            await db.execute("""
                INSERT INTO gsc_metrics
                    (post_id, date, clicks, impressions, ctr, avg_position, top_queries)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (post_id, date) DO UPDATE SET
                    clicks = EXCLUDED.clicks,
                    impressions = EXCLUDED.impressions,
                    ctr = EXCLUDED.ctr,
                    avg_position = EXCLUDED.avg_position,
                    top_queries = EXCLUDED.top_queries,
                    updated_at = NOW()
            """,
                post_id, date.fromisoformat(row_date),
                int(agg["clicks"]), int(agg["impressions"]),
                float(avg_ctr), float(avg_pos),
                top_queries_json,
            )
            synced += 1

        # Update site last_gsc_sync
        await db.execute(
            "UPDATE sites SET last_gsc_sync = NOW() WHERE id = $1", site_id,
        )

        logger.info("GSC sync complete for site %s: %d rows synced", site_id, synced)
        return {
            "synced": synced,
            "date_range": f"{start_date} to {end_date}",
            "gsc_site_url": gsc_site_url,
        }

    async def get_ranking_trends(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        days_back: int = 90,
    ) -> list[dict]:
        """Get ranking trends per post for decay detection."""
        rows = await db.fetch("""
            SELECT
                p.id AS post_id,
                p.title,
                p.url,
                -- Recent 30d vs prior 30d
                AVG(CASE WHEN gm.date >= CURRENT_DATE - 30 THEN gm.avg_position END) AS pos_recent,
                AVG(CASE WHEN gm.date < CURRENT_DATE - 30 AND gm.date >= CURRENT_DATE - 60 THEN gm.avg_position END) AS pos_prior,
                SUM(CASE WHEN gm.date >= CURRENT_DATE - 30 THEN gm.clicks END) AS clicks_recent,
                SUM(CASE WHEN gm.date < CURRENT_DATE - 30 AND gm.date >= CURRENT_DATE - 60 THEN gm.clicks END) AS clicks_prior,
                SUM(CASE WHEN gm.date >= CURRENT_DATE - $2 THEN gm.impressions END) AS total_impressions,
                SUM(CASE WHEN gm.date >= CURRENT_DATE - $2 THEN gm.clicks END) AS total_clicks,
                AVG(CASE WHEN gm.date >= CURRENT_DATE - 30 THEN gm.ctr END) AS avg_ctr,
                MIN(gm.avg_position) AS best_position
            FROM posts p
            JOIN gsc_metrics gm ON gm.post_id = p.id
            WHERE p.site_id = $1
            GROUP BY p.id, p.title, p.url
            HAVING COUNT(gm.date) >= 7
        """, site_id, days_back)
        return [dict(r) for r in rows]
