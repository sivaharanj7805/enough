"""Weekly ecosystem email report generation."""

import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)


class WeeklyReportService:
    """Generate and send weekly ecosystem health reports."""

    async def _get_current_metrics(self, db: asyncpg.Connection, site_id: UUID) -> dict:
        """Fetch current site health metrics."""
        # Get post counts by role
        total = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id
        ) or 0

        active = await db.fetchval(
            """SELECT COUNT(*) FROM posts p
               JOIN post_health ph ON ph.post_id = p.id
               WHERE p.site_id = $1 AND ph.role IN ('pillar', 'supporter')""",
            site_id,
        ) or 0

        dead = await db.fetchval(
            """SELECT COUNT(*) FROM posts p
               JOIN post_health ph ON ph.post_id = p.id
               WHERE p.site_id = $1 AND ph.role = 'dead_weight'""",
            site_id,
        ) or 0

        cannibalistic = await db.fetchval(
            """SELECT COUNT(DISTINCT post_id) FROM (
                 SELECT post_a_id AS post_id FROM cannibalization_pairs
                 WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
                 UNION
                 SELECT post_b_id AS post_id FROM cannibalization_pairs
                 WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
               ) sub""",
            site_id,
        ) or 0

        # Health score
        health_row = await db.fetchrow(
            """SELECT AVG(ph.composite_score) as avg_score
               FROM posts p JOIN post_health ph ON ph.post_id = p.id
               WHERE p.site_id = $1""",
            site_id,
        )
        health_score = float(health_row["avg_score"]) if health_row and health_row["avg_score"] else 0.0

        # Efficiency ratio
        efficiency = (active / total * 100) if total > 0 else 0.0

        return {
            "health_score": round(health_score, 1),
            "efficiency_ratio": round(efficiency, 1),
            "total_posts": total,
            "active_posts": active,
            "dead_posts": dead,
            "cannibalistic_posts": cannibalistic,
        }

    async def _get_previous_snapshot(
        self, db: asyncpg.Connection, site_id: UUID
    ) -> dict | None:
        """Fetch the most recent report snapshot."""
        row = await db.fetchrow(
            """SELECT health_score, efficiency_ratio, total_posts,
                      active_posts, dead_posts, cannibalistic_posts, snapshot_date
               FROM report_snapshots
               WHERE site_id = $1
               ORDER BY snapshot_date DESC LIMIT 1""",
            site_id,
        )
        if not row:
            return None
        return dict(row)

    async def _save_snapshot(
        self, db: asyncpg.Connection, site_id: UUID, metrics: dict
    ) -> None:
        """Save current metrics as a snapshot for future comparison."""
        today = date.today()
        await db.execute(
            """INSERT INTO report_snapshots
               (site_id, health_score, efficiency_ratio, total_posts,
                active_posts, dead_posts, cannibalistic_posts, snapshot_date)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (site_id, snapshot_date) DO UPDATE SET
                 health_score = EXCLUDED.health_score,
                 efficiency_ratio = EXCLUDED.efficiency_ratio,
                 total_posts = EXCLUDED.total_posts,
                 active_posts = EXCLUDED.active_posts,
                 dead_posts = EXCLUDED.dead_posts,
                 cannibalistic_posts = EXCLUDED.cannibalistic_posts""",
            site_id,
            metrics["health_score"],
            metrics["efficiency_ratio"],
            metrics["total_posts"],
            metrics["active_posts"],
            metrics["dead_posts"],
            metrics["cannibalistic_posts"],
            today,
        )

    def _format_delta(self, current: float, previous: float | None) -> str:
        """Format a metric delta string."""
        if previous is None:
            return str(current)
        delta = current - previous
        sign = "+" if delta >= 0 else ""
        return f"{previous} → {current} ({sign}{delta:.1f})"

    async def generate_report(self, db: asyncpg.Connection, site_id: UUID) -> dict:
        """Generate a weekly report with HTML and text bodies."""
        current = await self._get_current_metrics(db, site_id)
        previous = await self._get_previous_snapshot(db, site_id)

        # Get site name
        site = await db.fetchrow("SELECT name, domain FROM sites WHERE id = $1", site_id)
        site_name = site["name"] if site else "Your Site"
        site_domain = site["domain"] if site else ""

        # Calculate deltas
        prev_health = previous["health_score"] if previous else None
        prev_efficiency = previous["efficiency_ratio"] if previous else None

        health_delta = self._format_delta(current["health_score"], prev_health)
        efficiency_delta = self._format_delta(current["efficiency_ratio"], prev_efficiency)

        # Get top clusters that changed
        cluster_changes = await db.fetch(
            """SELECT label, ecosystem_state, health_score
               FROM clusters WHERE site_id = $1
               ORDER BY health_score DESC NULLS LAST LIMIT 5""",
            site_id,
        )

        # Get new cannibalization threats
        new_threats = await db.fetchval(
            """SELECT COUNT(*) FROM cannibalization_pairs cp
               JOIN clusters c ON c.id = cp.cluster_id
               WHERE c.site_id = $1
               AND cp.created_at > NOW() - INTERVAL '7 days'""",
            site_id,
        ) or 0

        # Get top consolidation opportunity
        quick_win = await db.fetchrow(
            """SELECT c.label, COUNT(p.id) as post_count
               FROM clusters c
               JOIN posts p ON p.cluster_id = c.id
               WHERE c.site_id = $1 AND c.ecosystem_state = 'swamp'
               GROUP BY c.id, c.label
               ORDER BY post_count DESC LIMIT 1""",
            site_id,
        )

        subject = f"Your Ecosystem This Week — {site_name}"

        # Build cluster section
        cluster_html = ""
        cluster_text = ""
        for c in cluster_changes:
            label = c["label"] or "Unnamed"
            state = c["ecosystem_state"] or "unknown"
            score = c["health_score"] or 0
            cluster_html += f'<tr><td style="padding:6px 12px;border-bottom:1px solid #1f2937;">{label}</td><td style="padding:6px 12px;border-bottom:1px solid #1f2937;">{state}</td><td style="padding:6px 12px;border-bottom:1px solid #1f2937;">{score:.1f}</td></tr>'
            cluster_text += f"  • {label} ({state}) — Score: {score:.1f}\n"

        # Quick win section
        qw_html = ""
        qw_text = ""
        if quick_win:
            qw_label = quick_win["label"] or "Unnamed cluster"
            qw_count = quick_win["post_count"]
            qw_html = f'<div style="background:#1a4731;padding:16px;border-radius:8px;margin:16px 0;"><strong style="color:#22c55e;">🎯 Quick Win of the Week</strong><br/><span style="color:#e2e8f0;">Consolidate <strong>{qw_label}</strong> — {qw_count} posts could become 1 strong pillar.</span></div>'
            qw_text = f"\n🎯 Quick Win: Consolidate '{qw_label}' — {qw_count} posts could become 1 strong pillar.\n"

        html_body = f"""
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#0a0f1a;color:#e2e8f0;padding:32px;border-radius:12px;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#22c55e;font-size:24px;margin:0;">Enough</h1>
    <p style="color:#94a3b8;font-size:14px;margin:4px 0 0 0;">{site_domain}</p>
  </div>

  <h2 style="font-size:20px;margin:0 0 16px 0;color:#e2e8f0;">Your Ecosystem This Week</h2>

  <div style="display:flex;gap:16px;margin-bottom:24px;">
    <div style="flex:1;background:#111827;padding:16px;border-radius:8px;border:1px solid #1f2937;">
      <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;">Content Health</div>
      <div style="font-size:20px;font-weight:600;margin-top:4px;">{health_delta}</div>
    </div>
    <div style="flex:1;background:#111827;padding:16px;border-radius:8px;border:1px solid #1f2937;">
      <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;">Efficiency</div>
      <div style="font-size:20px;font-weight:600;margin-top:4px;">{efficiency_delta}</div>
    </div>
  </div>

  <div style="background:#111827;padding:16px;border-radius:8px;border:1px solid #1f2937;margin-bottom:16px;">
    <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;margin-bottom:8px;">Posts Breakdown</div>
    <div style="font-size:14px;">
      Total: <strong>{current['total_posts']}</strong> •
      Active: <strong style="color:#22c55e;">{current['active_posts']}</strong> •
      Dead: <strong style="color:#6b7280;">{current['dead_posts']}</strong> •
      Cannibalistic: <strong style="color:#f97316;">{current['cannibalistic_posts']}</strong>
    </div>
  </div>

  {"<div style='background:#111827;padding:16px;border-radius:8px;border:1px solid #1f2937;margin-bottom:16px;'><div style='color:#94a3b8;font-size:12px;text-transform:uppercase;margin-bottom:8px;'>⚠️ New Threats</div><div style='font-size:14px;color:#f97316;'>" + str(new_threats) + " new cannibalization pairs detected this week</div></div>" if new_threats > 0 else ""}

  <div style="background:#111827;padding:16px;border-radius:8px;border:1px solid #1f2937;margin-bottom:16px;">
    <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;margin-bottom:8px;">Top Clusters</div>
    <table style="width:100%;font-size:14px;border-collapse:collapse;">
      <tr style="color:#94a3b8;font-size:12px;"><th style="text-align:left;padding:6px 12px;">Cluster</th><th style="text-align:left;padding:6px 12px;">State</th><th style="text-align:left;padding:6px 12px;">Score</th></tr>
      {cluster_html}
    </table>
  </div>

  {qw_html}

  <div style="text-align:center;margin-top:24px;">
    <a href="#" style="display:inline-block;background:#22c55e;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">See Your Full Landscape →</a>
  </div>

  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:12px;">
    Enough — Publish Less. Grow More.
  </div>
</div>"""

        text_body = f"""Your Ecosystem This Week — {site_name}

Content Health: {health_delta}
Efficiency: {efficiency_delta}

Posts: {current['total_posts']} total, {current['active_posts']} active, {current['dead_posts']} dead, {current['cannibalistic_posts']} cannibalistic
{"New threats: " + str(new_threats) + " cannibalization pairs this week" if new_threats > 0 else ""}

Top Clusters:
{cluster_text}
{qw_text}
Log in to see your full landscape.
"""

        # Save snapshot for next week's comparison
        await self._save_snapshot(db, site_id, current)

        return {
            "subject": subject,
            "html_body": html_body,
            "text_body": text_body.strip(),
        }

    async def send_report(self, db: asyncpg.Connection, site_id: UUID) -> bool:
        """Generate and send the weekly report for a site."""
        settings = get_settings()

        try:
            report = await self.generate_report(db, site_id)

            # Get user email
            user_email = await db.fetchval(
                """SELECT p.email FROM profiles p
                   JOIN sites s ON s.user_id = p.id::text
                   WHERE s.id = $1""",
                site_id,
            )

            if not user_email:
                logger.warning("No email found for site %s, skipping report", site_id)
                await self._record_history(db, site_id, report["subject"], "skipped")
                return False

            # Send via Resend if configured
            if settings.resend_api_key:
                import resend

                resend.api_key = settings.resend_api_key
                resend.Emails.send(
                    {
                        "from": settings.email_from,
                        "to": [user_email],
                        "subject": report["subject"],
                        "html": report["html_body"],
                        "text": report["text_body"],
                    }
                )
                logger.info("Weekly report sent to %s for site %s", user_email, site_id)
            else:
                logger.info(
                    "Resend not configured — report generated but not sent for site %s",
                    site_id,
                )

            await self._record_history(db, site_id, report["subject"], "sent")
            return True

        except Exception as e:
            logger.error("Failed to send report for site %s: %s", site_id, e)
            await self._record_history(
                db, site_id, f"Weekly Report (failed)", "failed"
            )
            return False

    async def send_all_reports(self, db: asyncpg.Connection) -> int:
        """Send weekly reports for all active sites (cron job entry point)."""
        sites = await db.fetch("SELECT id FROM sites")
        sent = 0
        for site in sites:
            if await self.send_report(db, site["id"]):
                sent += 1
        logger.info("Weekly reports sent: %d/%d", sent, len(sites))
        return sent

    async def _record_history(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        subject: str,
        status: str,
    ) -> None:
        """Record report send attempt in history."""
        await db.execute(
            """INSERT INTO report_history (site_id, subject, status)
               VALUES ($1, $2, $3)""",
            site_id,
            subject,
            status,
        )

    async def get_history(
        self, db: asyncpg.Connection, site_id: UUID, limit: int = 20
    ) -> list[dict]:
        """Get report history for a site."""
        rows = await db.fetch(
            """SELECT id, site_id, subject, status, sent_at
               FROM report_history
               WHERE site_id = $1
               ORDER BY sent_at DESC
               LIMIT $2""",
            site_id,
            limit,
        )
        return [dict(r) for r in rows]
