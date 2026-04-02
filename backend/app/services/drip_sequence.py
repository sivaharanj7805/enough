"""3-email drip sequence for audit leads via Resend."""

import asyncio
import base64
import html as html_mod
import logging
from datetime import UTC, datetime, timedelta
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
        cann_count = audit_data.get("cann_pair_count", 0)

        subject = "Your blog is fighting itself — here's the proof"
        html_body = self._email_1_html(blog_name, domain, score, rec_count, email=email, cann_count=cann_count)

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
                        "filename": f"tended-audit-{domain}.pdf",
                        "content": base64.b64encode(pdf_bytes).decode(),
                    }
                ],
            },
        )

        # Mark email 1 as sent
        now = datetime.now(UTC)
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
        html_body = self._email_1_html(blog_name, domain, score, rec_count, email=email)

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
        rec_type = rec_row["recommendation_type"] if rec_row else "optimize"

        # Difficulty based on rec type
        difficulty_map = {"redirect": "Easy", "merge": "Medium", "consolidate": "Medium", "expand": "Medium", "optimize": "Easy", "interlink": "Easy"}
        difficulty = difficulty_map.get(rec_type, "Medium")

        subject = f"{domain}: this one fix could boost your rankings"
        html_body = self._email_2_html(
            blog_name, domain, score, rec_count, rec_title, rec_summary, post_title,
            email=email, difficulty=difficulty,
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
        html_body = self._email_3_html(blog_name, domain, score, rec_count, email=email)

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
        """Wrap email content in Tended-branded template (white, professional)."""
        unsubscribe = f"https://usetended.io/unsubscribe?email={email}" if email else "#"
        return f"""
<div style="max-width:600px;margin:0 auto;font-family:'Inter',system-ui,sans-serif;background:#ffffff;color:#1e293b;padding:32px;border-radius:12px;border:1px solid #e5e7eb;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#16a34a;font-size:24px;margin:0;">Tended</h1>
    <p style="color:#64748b;font-size:12px;margin:4px 0 0 0;">Publish Less. Grow More.</p>
  </div>
  {inner_html}
  <div style="text-align:center;margin-top:32px;">
    <a href="https://usetended.io" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;">Subscribe to Tended &rarr;</a>
  </div>
  <div style="text-align:center;margin-top:24px;color:#94a3b8;font-size:11px;">
    <a href="{unsubscribe}" style="color:#94a3b8;text-decoration:underline;">Unsubscribe</a>
    &nbsp;&bull;&nbsp; Tended &mdash; Content Ecosystem Intelligence
  </div>
</div>"""

    def _email_1_html(self, blog_name: str, domain: str, score: int, rec_count: int, email: str = "", cann_count: int = 0) -> str:
        blog_name = html_mod.escape(blog_name)
        domain = html_mod.escape(domain)
        score_color = "#16a34a" if score >= 65 else "#ca8a04" if score >= 40 else "#dc2626"
        # Lead with the scariest finding
        if cann_count > 0:
            scary_lead = f'We found <strong>{cann_count} pairs of posts cannibalizing each other</strong> on {blog_name}. They\'re splitting your traffic and confusing Google about which page to rank.'
        else:
            scary_lead = f'We found <strong>{rec_count} issues</strong> holding back {blog_name} from ranking higher.'
        inner = f"""
  <span style="display:none;max-height:0;overflow:hidden;">We found {cann_count or rec_count} issues fighting your rankings...</span>
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">Your Blog Is Fighting Itself</h2>
  <p style="font-size:14px;color:#374151;">{scary_lead}</p>
  <div style="text-align:center;margin:24px 0;">
    <div style="font-size:48px;font-weight:700;color:{score_color};">{score}/100</div>
    <div style="color:#64748b;font-size:13px;">Blog Health Score</div>
  </div>
  <p style="font-size:14px;color:#374151;">Your full audit report is attached as a PDF. It includes:</p>
  <ul style="color:#374151;font-size:14px;padding-left:20px;">
    <li>Every cannibalization pair we found</li>
    <li>Top 5 posts needing immediate attention</li>
    <li>Your AI citability score vs. industry average</li>
  </ul>
  <p style="font-size:14px;color:#374151;">We also generated <strong>{rec_count} specific, actionable recommendations</strong>. Subscribe to see them all.</p>"""
        return self._base_wrapper(inner, email=email)

    def _email_2_html(
        self, blog_name: str, domain: str, score: int, rec_count: int,
        rec_title: str, rec_summary: str, post_title: str, email: str = "", difficulty: str = "Medium",
    ) -> str:
        blog_name = html_mod.escape(blog_name)
        domain = html_mod.escape(domain)
        rec_title = html_mod.escape(rec_title)
        rec_summary = html_mod.escape(rec_summary)
        post_title = html_mod.escape(post_title)
        diff_color = "#16a34a" if difficulty == "Easy" else "#ca8a04" if difficulty == "Medium" else "#dc2626"
        inner = f"""
  <span style="display:none;max-height:0;overflow:hidden;">Here's one of the {rec_count} fixes we found for {blog_name}...</span>
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">One of {rec_count} Fixes for {blog_name}</h2>
  <p style="color:#64748b;font-size:14px;">Remember your audit from a couple days ago? Here's a preview of what Tended found:</p>
  <div style="background:#f8fafc;padding:16px;border-radius:8px;border-left:4px solid #f97316;margin:20px 0;">
    <div style="color:#f97316;font-weight:600;font-size:14px;">{rec_title}</div>
    <div style="color:#374151;font-size:13px;margin-top:8px;">{rec_summary}</div>
    <div style="margin-top:8px;">
      <span style="display:inline-block;background:{diff_color}22;color:{diff_color};font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">{difficulty}</span>
      <span style="color:#64748b;font-size:12px;margin-left:8px;">Affects: {post_title}</span>
    </div>
  </div>
  <p style="font-size:14px;color:#374151;">This is just <strong>1 of {rec_count} recommendations</strong> we generated. Each one includes specific actions, estimated effort, and expected impact.</p>
  <p style="font-size:14px;color:#64748b;">Your blog scored <strong>{score}/100</strong>. Every point you gain means better rankings and more organic traffic.</p>"""
        return self._base_wrapper(inner, email=email)

    def _email_3_html(self, blog_name: str, domain: str, score: int, rec_count: int, email: str = "") -> str:
        blog_name = html_mod.escape(blog_name)
        domain = html_mod.escape(domain)
        # Conditionally color the score — don't red-wash decent scores
        score_color = "#16a34a" if score >= 65 else "#ca8a04" if score >= 40 else "#dc2626"
        score_bg = "#f0fdf4" if score >= 65 else "#fefce8" if score >= 40 else "#fef2f2"
        inner = f"""
  <span style="display:none;max-height:0;overflow:hidden;">Your blog is still fighting itself — {rec_count} fixes waiting...</span>
  <h2 style="font-size:18px;margin:0 0 8px;color:#111827;">Your Blog Is Still Fighting Itself</h2>
  <p style="color:#64748b;font-size:14px;">It's been 5 days since we audited <strong>{blog_name}</strong>, and nothing has changed.</p>
  <div style="background:{score_bg};padding:16px;border-radius:8px;margin:20px 0;text-align:center;">
    <div style="font-size:36px;font-weight:700;color:{score_color};">{score}/100</div>
    <div style="color:#64748b;font-size:13px;">Still your health score</div>
  </div>
  <p style="font-size:14px;color:#374151;">Every day you wait, your competing posts are splitting traffic, your orphan content is invisible to Google, and your thin posts are dragging down your domain authority.</p>
  <p style="font-size:14px;color:#374151;">We have <strong>{rec_count} specific, actionable fixes</strong> ready for you. Each one tells you exactly what to do, which post to fix, and what impact to expect.</p>
  <p style="font-size:14px;color:#16a34a;font-weight:600;">$149/month. 30-day money-back guarantee. Cancel anytime.</p>
  <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">
    <p style="font-size:12px;color:#64748b;">P.S. Know another content team or agency? Forward them this report &mdash; or have them request a free audit at <a href="https://usetended.io" style="color:#16a34a;">usetended.io</a>.</p>
  </div>"""
        return self._base_wrapper(inner, email=email)
