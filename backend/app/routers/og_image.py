"""OG image endpoint — returns a styled SVG for social sharing previews."""
import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.database import get_db
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap(text: str, max_chars: int = 52) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for w in words:
        if len(line) + len(w) + 1 <= max_chars:
            line = f"{line} {w}".strip()
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines[:3]  # max 3 lines


@router.get("/{site_id}/og-image")
async def og_image(
    site_id: UUID,
    db: Annotated[asyncpg.Connection, Depends(get_db)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> Response:
    """Generate a 1200×630 SVG social card for the audit report."""
    # Verify site ownership
    ownership = await db.fetchrow(
        "SELECT id FROM sites WHERE id = $1 AND user_id = $2", site_id, user_id
    )
    if not ownership:
        raise HTTPException(status_code=404, detail="Site not found")

    site = await db.fetchrow("SELECT domain FROM sites WHERE id = $1", site_id)
    domain = site["domain"] if site else "content audit"

    row = await db.fetchrow("""
        SELECT
            COUNT(DISTINCT p.id) AS posts,
            ROUND(AVG(phs.composite_score)) AS health,
            (SELECT COUNT(*) FROM cannibalization_pairs cp
             JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1) AS cann_pairs,
            (SELECT COUNT(*) FROM content_problems prob
             JOIN posts pp ON pp.id = prob.post_id WHERE pp.site_id = $1
               AND prob.problem_type = 'thin_content') AS thin
        FROM posts p
        LEFT JOIN post_health_scores phs ON phs.post_id = p.id
        WHERE p.site_id = $1
    """, site_id)

    posts = int(row["posts"] or 0)
    health = int(row["health"] or 0)
    cann = int(row["cann_pairs"] or 0)
    thin = int(row["thin"] or 0)

    # Health colour
    if health >= 70:
        health_color = "#22c55e"
    elif health >= 45:
        health_color = "#f59e0b"
    else:
        health_color = "#ef4444"

    domain_lines = _wrap(domain.upper())
    domain_svg = "".join(
        f'<tspan x="60" dy="{0 if i == 0 else 52}">{_escape(l)}</tspan>'
        for i, l in enumerate(domain_lines)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0a0f1a"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="card" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Accent bar -->
  <rect x="0" y="0" width="6" height="630" fill="#22c55e"/>

  <!-- Brand -->
  <text x="60" y="66" font-family="system-ui, sans-serif" font-size="22" font-weight="700"
        fill="#22c55e" letter-spacing="4">TENDED</text>
  <text x="168" y="66" font-family="system-ui, sans-serif" font-size="16" fill="#64748b">
    Content Intelligence</text>

  <!-- Domain headline -->
  <text font-family="system-ui, sans-serif" font-size="50" font-weight="800"
        fill="#e2e8f0" letter-spacing="-1">
    {domain_svg}
  </text>
  <text x="60" y="{180 + (len(domain_lines) - 1) * 52 + 10}"
        font-family="system-ui, sans-serif" font-size="24" fill="#94a3b8">
    Content Ecosystem Audit
  </text>

  <!-- Stat cards -->
  <rect x="60" y="390" width="240" height="140" rx="12" fill="url(#card)" stroke="#1e293b" stroke-width="1"/>
  <text x="80" y="435" font-family="system-ui, sans-serif" font-size="14" fill="#64748b">POSTS ANALYZED</text>
  <text x="80" y="495" font-family="system-ui, sans-serif" font-size="52" font-weight="800" fill="#e2e8f0">{posts}</text>

  <rect x="330" y="390" width="240" height="140" rx="12" fill="url(#card)" stroke="#1e293b" stroke-width="1"/>
  <text x="350" y="435" font-family="system-ui, sans-serif" font-size="14" fill="#64748b">HEALTH SCORE</text>
  <text x="350" y="495" font-family="system-ui, sans-serif" font-size="52" font-weight="800" fill="{health_color}">{health}</text>
  <text x="{350 + (2 if health >= 100 else 1) * 32 + 10}" y="495" font-family="system-ui, sans-serif" font-size="24" fill="#64748b">/100</text>

  <rect x="600" y="390" width="240" height="140" rx="12" fill="url(#card)" stroke="#1e293b" stroke-width="1"/>
  <text x="620" y="435" font-family="system-ui, sans-serif" font-size="14" fill="#64748b">CANN. PAIRS</text>
  <text x="620" y="495" font-family="system-ui, sans-serif" font-size="52" font-weight="800" fill="#f59e0b">{cann}</text>

  <rect x="870" y="390" width="240" height="140" rx="12" fill="url(#card)" stroke="#1e293b" stroke-width="1"/>
  <text x="890" y="435" font-family="system-ui, sans-serif" font-size="14" fill="#64748b">THIN CONTENT</text>
  <text x="890" y="495" font-family="system-ui, sans-serif" font-size="52" font-weight="800" fill="#ef4444">{thin}</text>

  <!-- Footer -->
  <text x="60" y="606" font-family="system-ui, sans-serif" font-size="16" fill="#334155">
    usetended.io · AI-powered content ecosystem intelligence
  </text>
</svg>"""

    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})
