"""3-email drip sequence for audit leads via Resend."""

import asyncio
import base64
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

# Drip schedule: email number → days after audit request
DRIP_SCHEDULE = {
    1: 0,   # Immediate: PDF audit attached
    2: 2,   # Day 2: One tantalizing recommendation example
    3: 5,   # Day 5: Urgency + final push
}


class DripSequenceService:
    """Manage the 3-email drip sequence for audit report leads."""

    async def schedule_drip(
        self,
        db: asyncpg.Connection,
        email: str,
        domain: str,
        site_id: UUID,
        audit_data: dict,
        pdf_bytes: bytes,
    ) -> None:
        """Schedule all 3 drip emails and immediately send email 1.

        Stores the drip schedule in the audit_drip_emails table.
        Email 1 is sent immediately with the PDF attached.
        Emails 2 and 3 are stored as pending for the cron to pick up.
        """
        now = datetime.now(timezone.utc)
        score = audit_data.get("overall_health", 0)
        rec_count = audit_data.get("rec_count", 0)
        blog_name = audit_data.get("site_name", domain)

        # Insert drip records for all 3 emails
        for email_num, delay_days in DRIP_SCHEDULE.items():
            send_at = now + timedelta(days=delay_days)
            status = "pending"
            await db.execute(
                """INSERT INTO audit_drip_emails
                   (email, domain, site_id, email_number, send_at, status,
                    score, rec_count, blog_name, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                   ON CONFLICT (email, site_id, email_number) DO NOTHING""",
                email, domain, site_id, email_num, send_at, status,
                score, rec_count, blog_name, now,
            )

        # Send email 1 immediately
        await self._send_email_1(db, email, domain, site_id, audit_data, pdf_bytes)

    async def process_pending_drips(self, db: asyncpg.Connection) -> int:
        """Process all pending drip emails that are due. Returns count sent."""
        now = datetime.now(timezone.utc)
        rows = await db.fetch(
            """SELECT id, email, domain, site_id, email_number, score, rec_count, blog_name
               FROM audit_drip_emails
               WHERE status = 'pending' AND send_at <= $1
               ORDER BY send_at ASC
               LIMIT 100""",
            now,
        )

        sent = 0
        for row in rows:
            try:
                # Check email opt-out before sending
                opted_out = await db.fetchval(
                    "SELECT 1 FROM email_optouts WHERE email = $1",
                    row["email"].lower().strip(),
                )
                if opted_out:
                    await db.execute(
                        "UPDATE audit_drip_emails SET status = 'skipped', error = 'opted out' WHERE id = $1",
                        row["id"],
                    )
                    continue

                email_num = row["email_number"]
                if email_num == 1:
                    # Email 1 should already be sent during schedule_drip,
                    # but handle retries here
                    await self._send_email_1_simple(
                        row["email"], row["domain"], row["site_id"],
                        row["score"], row["rec_count"], row["blog_name"],
                    )
                elif email_num == 2:
                    await self._send_email_2(
                        db, row["email"], row["domain"], row["site_id"],
                        row["score"], row["rec_count"], row["blog_name"],
                    )
                elif email_num == 3:
                    await self._send_email_3(
                        row["email"], row["domain"], row["site_id"],
                        row["score"], row["rec_count"], row["blog_name"],
                    )

                await db.execute(
                    "UPDATE audit_drip_emails SET status = 'sent', sent_at = $1 WHERE id = $2",
                    now, row["id"],
                )
                sent += 1

            except Exception as e:
                logger.error(
                    "Drip email %d failed for %s: %s", row["email_number"], row["email"], e,
                )
                await db.execute(
                    "UPDATE audit_drip_emails SET status = 'failed', error = $1 WHERE id = $2",
                    str(e)[:500], row["id"],
                )

        logger.info("Processed %d drip emails (%d sent)", len(rows), sent)
        return sent

    # ── Email 1: Immediate — PDF audit attached ──

    async def _send_email_1(
        self,
        db: asyncpg.Connection,
        email: str,
        domain: str,
        site_id: UUID,
        audit_data: dict,
        pdf_bytes: bytes,
    ) -> None:
        """Send email 1 with the PDF audit report attached."""
        settings = get_settings()
        if not settings.resend_api_key:
            logger.info("Resend not configured — skipping drip email 1 for %s", email)
            return

        score = audit_data.get("overall_health", 0)
        rec_count = audit_data.get("rec_count", 0)
        blog_name = audit_data.get("site_name", domain)

        subject = f"Your blog health score: {score}/100 — Audit Report"
        html_body = self._email_1_html(blog_name, domain, score, rec_count)

        import resend
        resend.api_key = settings.resend_api_key

        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "html": html_body,
                "attachments": [
                    {
                        "filename": f"enough-audit-{domain}.pdf",
                        "content": base64.b64encode(pdf_bytes).decode(),
                    }
                ],
            },
        )

        # Mark email 1 as sent
        now = datetime.now(timezone.utc)
        await db.execute(
            """UPDATE audit_drip_emails SET status = 'sent', sent_at = $1
               WHERE email = $2 AND site_id = $3 AND email_number = 1""",
            now, email, site_id,
        )
        logger.info("Drip email 1 sent to %s for %s", email, domain)

    async def _send_email_1_simple(
        self, email: str, domain: str, site_id: UUID,
        score: int, rec_count: int, blog_name: str,
    ) -> None:
        """Send email 1 without PDF attachment (retry path)."""
        settings = get_settings()
        if not settings.resend_api_key:
            return

        subject = f"Your blog health score: {score}/100 — Audit Report"
        html_body = self._email_1_html(blog_name, domain, score, rec_count)

        import resend
        resend.api_key = settings.resend_api_key
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "html": html_body,
            },
        )

    # ── Email 2: Day 2 — One tantalizing recommendation ──

    async def _send_email_2(
        self,
        db: asyncpg.Connection,
        email: str,
        domain: str,
        site_id: UUID,
        score: int,
        rec_count: int,
        blog_name: str,
    ) -> None:
        """Send email 2: one example recommendation to tease the full report."""
        settings = get_settings()
        if not settings.resend_api_key:
            return

        # Fetch one high-priority recommendation
        rec_row = await db.fetchrow(
            """SELECT r.title, r.summary, r.recommendation_type, p.title AS post_title
               FROM recommendations r
               JOIN posts p ON p.id = r.post_id
               WHERE r.site_id = $1
               ORDER BY CASE r.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3 ELSE 4 END
               LIMIT 1""",
            site_id,
        )

        rec_title = rec_row["title"] if rec_row else "Consolidate competing posts"
        rec_summary = rec_row["summary"] if rec_row else "Multiple posts are competing for the same keywords."
        post_title = rec_row["post_title"] if rec_row else "your top post"

        subject = f"Here's one of the {rec_count} fixes we found for {blog_name}"
        html_body = self._email_2_html(
            blog_name, domain, score, rec_count, rec_title, rec_summary, post_title,
        )

        import resend
        resend.api_key = settings.resend_api_key
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "html": html_body,
            },
        )
        logger.info("Drip email 2 sent to %s for %s", email, domain)

    # ── Email 3: Day 5 — Urgency ──

    async def _send_email_3(
        self,
        email: str,
        domain: str,
        site_id: UUID,
        score: int,
        rec_count: int,
        blog_name: str,
    ) -> None:
        """Send email 3: urgency — your blog is still fighting itself."""
        settings = get_settings()
        if not settings.resend_api_key:
            return

        subject = "Your blog is still fighting itself"
        html_body = self._email_3_html(blog_name, domain, score, rec_count)

        import resend
        resend.api_key = settings.resend_api_key
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "html": html_body,
            },
        )
        logger.info("Drip email 3 sent to %s for %s", email, domain)

    # ── HTML Templates ──

    def _base_wrapper(self, inner_html: str, email: str = "") -> str:
        """Wrap email content in Enough-branded template (white, professional)."""
        unsubscribe = f"https://enough.app/unsubscribe?email={email}" if email else "#"
        return f"""
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;padding:32px;border-radius:12px;border:1px solid #e5e7eb;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Enough</h1>
    <p style="color:#64748b;font-size:12px;margin:4px 0 0 0;">Publish Less. Grow More.</p>
  </div>
  {inner_html}
  <div style="text-align:center;margin-top:32px;">
    <a href="https://enough.app" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Subscribe to Enough &rarr;</a>
  </div>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:11px;">
    <a href="{unsubscribe}" style="color:#94a3b8;text-decoration:underline;">Unsubscribe</a>
    &nbsp;&bull;&nbsp; Enough &mdash; Content Ecosystem Intelligence
  </div>
</div>"""

    def _email_1_html(self, blog_name: str, domain: str, score: int, rec_count: int) -> str:
        score_color = "#16a34a" if score >= 65 else "#ca8a04" if score >= 40 else "#dc2626"
        inner = f"""
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">Your Blog Health Audit is Ready</h2>
  <p style="color:#64748b;font-size:14px;">Hi! We've finished analyzing <strong>{blog_name}</strong>.</p>
  <div style="text-align:center;margin:24px 0;">
    <div style="font-size:48px;font-weight:700;color:{score_color};">{score}/100</div>
    <div style="color:#64748b;font-size:13px;">Blog Health Score</div>
  </div>
  <p style="font-size:14px;color:#374151;">Your full audit report is attached as a PDF. Inside you'll find:</p>
  <ul style="color:#374151;font-size:14px;padding-left:20px;">
    <li>Issue breakdown by category</li>
    <li>Top 5 posts needing attention</li>
    <li>Key findings about your content ecosystem</li>
  </ul>
  <p style="font-size:14px;color:#374151;">We also generated <strong>{rec_count} specific recommendations</strong> to improve your blog. Subscribe to see them all.</p>"""
        return self._base_wrapper(inner)

    def _email_2_html(
        self, blog_name: str, domain: str, score: int, rec_count: int,
        rec_title: str, rec_summary: str, post_title: str,
    ) -> str:
        inner = f"""
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">One of {rec_count} Fixes for {blog_name}</h2>
  <p style="color:#64748b;font-size:14px;">Remember your audit from a couple days ago? Here's a preview of what Enough found:</p>
  <div style="background:#f8fafc;padding:16px;border-radius:8px;border-left:4px solid #f97316;margin:20px 0;">
    <div style="color:#f97316;font-weight:600;font-size:14px;">{rec_title}</div>
    <div style="color:#374151;font-size:13px;margin-top:8px;">{rec_summary}</div>
    <div style="color:#64748b;font-size:12px;margin-top:8px;">Affects: {post_title}</div>
  </div>
  <p style="font-size:14px;color:#374151;">This is just <strong>1 of {rec_count} recommendations</strong> we generated. Each one includes specific actions, estimated effort, and expected impact.</p>
  <p style="font-size:14px;color:#64748b;">Your blog scored <strong>{score}/100</strong>. Every point you gain means better rankings and more organic traffic.</p>"""
        return self._base_wrapper(inner)

    def _email_3_html(self, blog_name: str, domain: str, score: int, rec_count: int) -> str:
        inner = f"""
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">Your Blog Is Still Fighting Itself</h2>
  <p style="color:#64748b;font-size:14px;">It's been 5 days since we audited <strong>{blog_name}</strong>, and nothing has changed.</p>
  <div style="background:#fef2f2;padding:16px;border-radius:8px;margin:20px 0;text-align:center;">
    <div style="font-size:36px;font-weight:700;color:#dc2626;">{score}/100</div>
    <div style="color:#64748b;font-size:13px;">Still your health score</div>
  </div>
  <p style="font-size:14px;color:#374151;">Every day you wait, your competing posts are splitting traffic, your orphan content is invisible to Google, and your thin posts are dragging down your domain authority.</p>
  <p style="font-size:14px;color:#374151;">We have <strong>{rec_count} specific, actionable fixes</strong> ready for you. Each one tells you exactly what to do, which post to fix, and what impact to expect.</p>
  <p style="font-size:14px;color:#16a34a;font-weight:600;">$99/month. 30-day money-back guarantee. Cancel anytime.</p>
  <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">
    <p style="font-size:12px;color:#64748b;">P.S. Know another content team or agency? Forward them this report &mdash; or have them request a free audit at <a href="https://enough.app" style="color:#16a34a;">enough.app</a>.</p>
  </div>"""
        return self._base_wrapper(inner)
