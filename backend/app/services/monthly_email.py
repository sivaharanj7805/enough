"""Monthly re-analysis email — the return trigger.

Sends a personalized monthly email to each paid user with:
- Health score delta (previous → current)
- Number of recommendations completed in the last 30 days
- Number of new issues detected
- CTA to log in and review

"Your content health changed: 54 → 57. You completed 23 recommendations.
3 new issues detected."
"""

import asyncio
import logging

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_monthly_report(
    db: asyncpg.Connection,
    site_id,
    email: str,
    domain: str,
) -> bool:
    """Send a monthly health report email for a site.

    Returns True if sent successfully, False otherwise.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured — skipping monthly email for %s", email)
        return False

    # Fetch health score history (last 2 entries for delta)
    history = await db.fetch(
        """SELECT score, analyzed_at FROM health_score_history
           WHERE site_id = $1 ORDER BY analyzed_at DESC LIMIT 2""",
        site_id,
    )

    if not history:
        logger.info("No health history for site %s — skipping monthly email", site_id)
        return False

    current_score = round(float(history[0]["score"]))
    prev_score = round(float(history[1]["score"])) if len(history) >= 2 else None
    score_delta = current_score - prev_score if prev_score is not None else None
    last_analyzed = history[0]["analyzed_at"]

    # Completed recommendations in last 30 days
    completed_count = await db.fetchval(
        """SELECT COUNT(*) FROM recommendations
           WHERE site_id = $1 AND status = 'completed'
             AND updated_at > NOW() - INTERVAL '30 days'""",
        site_id,
    ) or 0

    # New issues in last 30 days
    new_issue_count = await db.fetchval(
        """SELECT COUNT(*) FROM content_problems cp
           JOIN posts p ON p.id = cp.post_id
           WHERE p.site_id = $1 AND cp.resolved_at IS NULL
             AND cp.detected_at > NOW() - INTERVAL '30 days'""",
        site_id,
    ) or 0

    # Pending recommendations
    pending_count = await db.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND status = 'pending'",
        site_id,
    ) or 0

    # Build email
    delta_text = ""
    if score_delta is not None:
        if score_delta > 0:
            delta_text = f"<span style='color:#22c55e;font-weight:600'>+{score_delta} points</span>"
        elif score_delta < 0:
            delta_text = f"<span style='color:#ef4444;font-weight:600'>{score_delta} points</span>"
        else:
            delta_text = "<span style='color:#9BA1AD'>unchanged</span>"

    score_line = f"<strong>{current_score}/100</strong>"
    if prev_score is not None and score_delta != 0:
        score_line = f"{prev_score} &rarr; <strong>{current_score}</strong> ({delta_text})"

    subject = f"Monthly Content Health Report — {domain}"
    if score_delta is not None and score_delta > 0:
        subject = f"{domain}: Health score up {score_delta} points this month"
    elif score_delta is not None and score_delta < 0:
        subject = f"{domain}: Health score dropped {abs(score_delta)} points — review needed"

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;color:#E8EAED;background:#0B0D11;padding:32px 24px;border-radius:12px;">
      <div style="margin-bottom:24px;">
        <span style="font-size:14px;font-weight:600;color:#3B82F6;">Tended</span>
        <span style="font-size:12px;color:#9BA1AD;margin-left:8px;">Monthly Report</span>
      </div>

      <h1 style="font-size:20px;font-weight:700;margin:0 0 8px;">Content Health: {score_line}</h1>

      <div style="margin:20px 0;padding:16px;background:#13151B;border:1px solid #23262F;border-radius:8px;">
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr>
            <td style="padding:8px 0;color:#9BA1AD;">Recommendations completed</td>
            <td style="padding:8px 0;text-align:right;font-weight:600;color:#22c55e;">{completed_count}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#9BA1AD;">New issues detected</td>
            <td style="padding:8px 0;text-align:right;font-weight:600;color:{'#ef4444' if new_issue_count > 0 else '#9BA1AD'};">{new_issue_count}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#9BA1AD;">Pending recommendations</td>
            <td style="padding:8px 0;text-align:right;font-weight:600;color:#f59e0b;">{pending_count}</td>
          </tr>
        </table>
      </div>

      <a href="https://app.usetended.io/today"
         style="display:inline-block;padding:10px 24px;background:#3B82F6;color:white;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;">
        Review Your Dashboard &rarr;
      </a>

      <p style="margin-top:24px;font-size:12px;color:#64748b;">
        Last analyzed: {last_analyzed.strftime('%B %d, %Y') if last_analyzed else 'N/A'}
      </p>
    </div>
    """

    try:
        import resend
        resend.api_key = settings.resend_api_key
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "html": html,
            },
        )
        logger.info("Sent monthly report to %s for %s", email, domain)
        return True
    except Exception:
        logger.warning("Failed to send monthly report to %s", email, exc_info=True)
        return False


async def send_all_monthly_reports(db: asyncpg.Connection) -> int:
    """Send monthly reports to all active paid users. Returns count sent."""
    # Find all active paid sites with users
    sites = await db.fetch(
        """SELECT s.id AS site_id, s.domain, u.email
           FROM sites s
           JOIN subscriptions sub ON sub.user_id = s.user_id
           JOIN auth.users u ON u.id::text = s.user_id
           WHERE sub.tier IN ('growth', 'scale') AND sub.status = 'active'
             AND s.domain IS NOT NULL""",
    )

    sent = 0
    for site in sites:
        ok = await send_monthly_report(
            db, site["site_id"], site["email"], site["domain"],
        )
        if ok:
            sent += 1
    return sent
