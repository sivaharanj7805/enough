"""Smart alerts — proactive notifications for important changes.

Generates alerts from change detection results and stores them in
the alerts table. Supports email delivery via Resend.

Alert types:
  ranking_drop       — Post dropped 5+ positions
  health_decline     — Health score dropped 10+ points
  new_cannibalization — New cannibalization pair detected
  velocity_decline   — Publishing rate dropped significantly
  new_problems       — Multiple new problems detected
  pillar_at_risk     — Pillar post lost status
  recommendation_impact — Completed recommendation showed results

This is what makes users open the tool daily instead of monthly.
"""

import json
import logging
from uuid import UUID

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)


class AlertManager:
    """Create, store, and deliver smart alerts."""

    async def generate_alerts_from_changes(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        changes: list[dict],
    ) -> int:
        """Convert detected changes into stored alerts.

        Returns number of alerts created.
        """
        created = 0
        for change in changes:
            await db.execute(
                """
                INSERT INTO alerts
                    (site_id, post_id, alert_type, severity,
                     title, message, details)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                site_id,
                change.get("post_id"),
                change["type"],
                change["severity"],
                change["title"],
                change["message"],
                json.dumps(change.get("details", {})),
            )
            created += 1

        logger.info("Created %d alerts for site %s", created, site_id)
        return created

    async def get_unread_alerts(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        limit: int = 50,
    ) -> list[dict]:
        """Get unread alerts for a site, newest first."""
        rows = await db.fetch(
            """
            SELECT id, post_id, alert_type, severity, title, message,
                   details, created_at
            FROM alerts
            WHERE site_id = $1 AND NOT is_read
            ORDER BY created_at DESC
            LIMIT $2
            """,
            site_id, limit,
        )
        return [dict(r) for r in rows]

    async def mark_read(
        self,
        db: asyncpg.Connection,
        alert_id: UUID,
    ) -> None:
        """Mark an alert as read."""
        await db.execute(
            "UPDATE alerts SET is_read = TRUE WHERE id = $1", alert_id,
        )

    async def mark_all_read(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> int:
        """Mark all alerts for a site as read. Returns count."""
        result = await db.execute(
            "UPDATE alerts SET is_read = TRUE WHERE site_id = $1 AND NOT is_read",
            site_id,
        )
        # asyncpg returns "UPDATE N"
        count = int(result.split()[-1]) if result else 0
        return count

    async def get_alert_summary(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> dict:
        """Get alert summary for dashboard display."""
        counts = await db.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE NOT is_read) AS unread,
                COUNT(*) FILTER (WHERE NOT is_read AND severity = 'critical') AS critical,
                COUNT(*) FILTER (WHERE NOT is_read AND severity = 'warning') AS warnings,
                COUNT(*) FILTER (WHERE NOT is_read AND severity = 'info') AS info,
                COUNT(*) AS total
            FROM alerts
            WHERE site_id = $1
            """,
            site_id,
        )
        return dict(counts) if counts else {
            "unread": 0, "critical": 0, "warnings": 0, "info": 0, "total": 0,
        }

    async def generate_email_digest(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> str | None:
        """Generate HTML email digest of unread alerts.

        Returns HTML string or None if no unread alerts.
        """
        alerts = await self.get_unread_alerts(db, site_id, limit=20)
        if not alerts:
            return None

        site = await db.fetchrow(
            "SELECT domain FROM sites WHERE id = $1", site_id,
        )
        domain = site["domain"] if site else "your site"

        severity_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}

        rows_html = ""
        for alert in alerts:
            emoji = severity_emoji.get(alert["severity"], "ℹ️")
            rows_html += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                    {emoji} <strong>{alert['title']}</strong><br/>
                    <span style="color: #718096; font-size: 14px;">{alert['message']}</span>
                </td>
            </tr>"""

        html = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1a202c;">Enough Alert Digest — {domain}</h2>
            <p style="color: #4a5568;">You have {len(alerts)} new alert{'s' if len(alerts) != 1 else ''}:</p>
            <table style="width: 100%; border-collapse: collapse;">
                {rows_html}
            </table>
            <p style="color: #718096; font-size: 13px; margin-top: 24px;">
                Log in to see full details and take action.
            </p>
        </div>
        """
        return html
