"""Redirect Push — Push 301 redirects to WordPress via REST API."""

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
import asyncpg

logger = logging.getLogger(__name__)


class RedirectPusher:
    """Push and verify redirect maps to WordPress sites."""

    async def check_redirection_plugin(
        self, wordpress_url: str, app_password: str
    ) -> bool:
        """Check if the Redirection plugin REST API is available."""
        url = f"{wordpress_url.rstrip('/')}/wp-json/redirection/v1/redirect"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Basic {app_password}"},
                )
                return resp.status_code in (200, 401, 403)
        except Exception as e:
            logger.debug("Redirection plugin check failed: %s", e)
            return False

    async def push_redirects(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        redirect_map: list[dict[str, str]],
    ) -> dict:
        """Push redirects to WordPress and log results."""
        # Fetch site WordPress config
        site = await db.fetchrow(
            """
            SELECT wordpress_url, wordpress_app_password
            FROM sites WHERE id = $1
            """,
            site_id,
        )
        if not site or not site["wordpress_url"]:
            raise ValueError("Site is not a WordPress site or missing WordPress URL")

        from app.utils.encryption import decrypt_value

        wp_url = site["wordpress_url"].rstrip("/")
        app_password = ""
        if site["wordpress_app_password"]:
            app_password = decrypt_value(site["wordpress_app_password"])

        results: list[dict] = []
        pushed = 0
        failed = 0

        has_plugin = await self.check_redirection_plugin(wp_url, app_password)

        async with httpx.AsyncClient(timeout=15.0) as client:
            for entry in redirect_map:
                old_url = entry["old_url"]
                new_url = entry["new_url"]
                now = datetime.now(timezone.utc)

                try:
                    if has_plugin:
                        # Use Redirection plugin API
                        resp = await client.post(
                            f"{wp_url}/wp-json/redirection/v1/redirect",
                            json={
                                "url": old_url,
                                "action_data": {"url": new_url},
                                "action_type": "url",
                                "action_code": 301,
                                "match_type": "url",
                                "group_id": 1,
                            },
                            headers={
                                "Authorization": f"Basic {app_password}",
                                "Content-Type": "application/json",
                            },
                        )
                        if resp.status_code in (200, 201):
                            status = "pushed"
                            pushed += 1
                            error = None
                        else:
                            status = "failed"
                            failed += 1
                            error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    else:
                        # Fallback: create redirect via WP REST API custom endpoint
                        # This assumes a simple mu-plugin or functions.php snippet
                        resp = await client.post(
                            f"{wp_url}/wp-json/wp/v2/settings",
                            json={
                                "enough_redirect": {
                                    "old_url": old_url,
                                    "new_url": new_url,
                                    "type": 301,
                                }
                            },
                            headers={
                                "Authorization": f"Basic {app_password}",
                                "Content-Type": "application/json",
                            },
                        )
                        if resp.status_code in (200, 201):
                            status = "pushed"
                            pushed += 1
                            error = None
                        else:
                            status = "failed"
                            failed += 1
                            error = f"HTTP {resp.status_code}: {resp.text[:200]}"

                except Exception as e:
                    status = "failed"
                    failed += 1
                    error = str(e)[:200]
                    logger.error("Redirect push failed for %s → %s: %s", old_url, new_url, e)

                # Log to DB (upsert — deduplicate on site + old_url)
                await db.execute(
                    """
                    INSERT INTO redirect_log
                        (site_id, old_url, new_url, status, pushed_at, error)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (site_id, old_url) DO UPDATE SET
                        new_url = EXCLUDED.new_url,
                        status = EXCLUDED.status,
                        pushed_at = EXCLUDED.pushed_at,
                        error = EXCLUDED.error
                    """,
                    site_id,
                    old_url,
                    new_url,
                    status,
                    now if status == "pushed" else None,
                    error,
                )

                results.append({
                    "old_url": old_url,
                    "new_url": new_url,
                    "status": status,
                    "pushed_at": now.isoformat() if status == "pushed" else None,
                    "verified_at": None,
                    "error": error,
                })

        logger.info(
            "Redirect push for site %s: %d pushed, %d failed out of %d",
            site_id, pushed, failed, len(redirect_map),
        )
        return {
            "site_id": site_id,
            "entries": results,
            "total": len(redirect_map),
            "pushed": pushed,
            "verified": 0,
            "failed": failed,
        }

    async def get_status(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> dict:
        """Get status of all redirect pushes for a site."""
        rows = await db.fetch(
            """
            SELECT old_url, new_url, status, pushed_at, verified_at, error
            FROM redirect_log
            WHERE site_id = $1
            ORDER BY created_at DESC
            """,
            site_id,
        )

        entries = [dict(r) for r in rows]
        total = len(entries)
        pushed = sum(1 for e in entries if e["status"] in ("pushed", "verified"))
        verified = sum(1 for e in entries if e["status"] == "verified")
        failed = sum(1 for e in entries if e["status"] == "failed")

        return {
            "site_id": site_id,
            "entries": entries,
            "total": total,
            "pushed": pushed,
            "verified": verified,
            "failed": failed,
        }

    async def verify_redirects(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> dict:
        """Verify all pushed redirects are actually working."""
        rows = await db.fetch(
            """
            SELECT id, old_url, new_url, status
            FROM redirect_log
            WHERE site_id = $1 AND status = 'pushed'
            """,
            site_id,
        )

        site = await db.fetchrow(
            "SELECT domain FROM sites WHERE id = $1", site_id
        )
        domain = site["domain"] if site else ""

        verified = 0
        failed = 0
        now = datetime.now(timezone.utc)

        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=False
        ) as client:
            for row in rows:
                old_url = row["old_url"]
                # Build full URL if relative
                check_url = old_url
                if not old_url.startswith("http"):
                    check_url = f"https://{domain}{old_url}"

                try:
                    resp = await client.get(check_url)
                    if resp.status_code in (301, 302, 307, 308):
                        location = resp.headers.get("location", "")
                        new_url = row["new_url"]
                        if location == new_url or location.endswith(new_url) or location.split("?")[0].endswith(new_url):
                            await db.execute(
                                """
                                UPDATE redirect_log
                                SET status = 'verified', verified_at = $2
                                WHERE id = $1
                                """,
                                row["id"],
                                now,
                            )
                            verified += 1
                        else:
                            await db.execute(
                                """
                                UPDATE redirect_log
                                SET status = 'failed',
                                    error = $2
                                WHERE id = $1
                                """,
                                row["id"],
                                f"Redirects to {location} instead of {row['new_url']}",
                            )
                            failed += 1
                    else:
                        await db.execute(
                            """
                            UPDATE redirect_log
                            SET status = 'failed',
                                error = $2
                            WHERE id = $1
                            """,
                            row["id"],
                            f"HTTP {resp.status_code}, not a redirect",
                        )
                        failed += 1

                except Exception as e:
                    await db.execute(
                        """
                        UPDATE redirect_log
                        SET status = 'failed', error = $2
                        WHERE id = $1
                        """,
                        row["id"],
                        str(e)[:200],
                    )
                    failed += 1

        logger.info(
            "Redirect verification for site %s: %d verified, %d failed",
            site_id, verified, failed,
        )

        # Return updated status
        return await self.get_status(db, site_id)
