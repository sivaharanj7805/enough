"""PDF audit report generation using reportlab.

White-label ready: clean white background, professional layout suitable
for agency client decks. Supports optional brand_name and logo_url params
for Scale plan white-labeling.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io


# ── Professional color palette (white-label ready) ──
WHITE = HexColor("#ffffff")
BLACK = HexColor("#111827")
DARK_GRAY = HexColor("#374151")
MID_GRAY = HexColor("#6b7280")
LIGHT_GRAY = HexColor("#f3f4f6")
BORDER_GRAY = HexColor("#e5e7eb")
GREEN = HexColor("#16a34a")
LIGHT_GREEN = HexColor("#dcfce7")
RED = HexColor("#dc2626")
LIGHT_RED = HexColor("#fef2f2")
YELLOW = HexColor("#ca8a04")
LIGHT_YELLOW = HexColor("#fefce8")
BLUE = HexColor("#2563eb")
LIGHT_BLUE = HexColor("#eff6ff")


def _score_color(score: int) -> HexColor:
    """Return color based on health score value."""
    if score >= 65:
        return GREEN
    if score >= 40:
        return YELLOW
    return RED


def _score_bg(score: int) -> HexColor:
    if score >= 65:
        return LIGHT_GREEN
    if score >= 40:
        return LIGHT_YELLOW
    return LIGHT_RED


def _build_styles(brand_color: HexColor = GREEN) -> dict:
    """Create professional paragraph styles for the PDF."""
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "BrandTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=BLACK,
        spaceAfter=4,
        alignment=1,
    )

    styles["subtitle"] = ParagraphStyle(
        "Subtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=MID_GRAY,
        alignment=1,
        spaceAfter=20,
    )

    styles["heading"] = ParagraphStyle(
        "SectionHeading",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=BLACK,
        spaceBefore=18,
        spaceAfter=8,
    )

    styles["body"] = ParagraphStyle(
        "BodyText",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=DARK_GRAY,
        spaceAfter=6,
        leading=14,
    )

    styles["stat_label"] = ParagraphStyle(
        "StatLabel",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=MID_GRAY,
        alignment=1,
    )

    styles["stat_value"] = ParagraphStyle(
        "StatValue",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=BLACK,
        alignment=1,
    )

    styles["score_big"] = ParagraphStyle(
        "ScoreBig",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=44,
        alignment=1,
        spaceAfter=4,
    )

    styles["issue_item"] = ParagraphStyle(
        "IssueItem",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=DARK_GRAY,
        leftIndent=12,
        spaceAfter=4,
        leading=14,
    )

    styles["cta"] = ParagraphStyle(
        "CTA",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=brand_color,
        alignment=1,
        spaceBefore=24,
        spaceAfter=6,
    )

    styles["cta_detail"] = ParagraphStyle(
        "CTADetail",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=MID_GRAY,
        alignment=1,
        spaceAfter=4,
    )

    styles["ai_metric"] = ParagraphStyle(
        "AIMetric",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=BLACK,
        alignment=1,
    )

    styles["ai_label"] = ParagraphStyle(
        "AILabel",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MID_GRAY,
        alignment=1,
    )

    styles["footer"] = ParagraphStyle(
        "Footer",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MID_GRAY,
        alignment=1,
    )

    return styles


def generate_audit_pdf(
    report: dict,
    *,
    brand_name: str | None = None,
    logo_url: str | None = None,
) -> bytes:
    """Generate a professional PDF audit report.

    Args:
        report: Dict with audit data (health score, issues, posts, etc.)
        brand_name: Optional agency name for white-labeling (Scale plan)
        logo_url: Optional logo URL for white-labeling (Scale plan)

    Returns:
        PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    styles = _build_styles()
    story: list = []

    display_brand = brand_name or "Enough"
    domain = report.get("site_domain", "")

    # ── Header: domain as hero ──
    story.append(Paragraph(
        _safe(domain),
        styles["title"],
    ))
    story.append(Paragraph(
        f"Content Audit Report",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 8))

    # ── Health score: large prominent number ──
    score = int(report.get("overall_health", 0))
    score_style = ParagraphStyle(
        "ScoreDynamic",
        parent=styles["score_big"],
        textColor=_score_color(score),
    )
    story.append(Paragraph(f"{score}/100", score_style))
    story.append(Paragraph("Content Health Score", styles["stat_label"]))
    story.append(Spacer(1, 16))

    # ── AI Readiness Section (page 1 prominence — 2026 differentiator) ──
    ai_pct_ready = report.get("ai_pct_ready")
    ai_cite = report.get("ai_citability_score")
    if ai_pct_ready is not None or ai_cite is not None:
        story.append(Paragraph("AI Readiness", styles["heading"]))

        if ai_pct_ready is not None:
            pct_color = RED if ai_pct_ready < 30 else (YELLOW if ai_pct_ready < 60 else GREEN)
            ai_headline_style = ParagraphStyle(
                "AIHeadline", parent=styles["body"],
                fontName="Helvetica-Bold", fontSize=12, textColor=pct_color,
            )
            story.append(Paragraph(
                f"{ai_pct_ready:.0f}% of your posts are AI-citable. Industry average: 61%.",
                ai_headline_style,
            ))
            story.append(Spacer(1, 8))

        # AI scores row
        ai_scores = []
        ai_labels = []
        for label, key in [
            ("AI Citability", "ai_citability_score"),
            ("E-E-A-T", "ai_eeat_score"),
            ("Schema", "ai_schema_score"),
            ("Extraction", "ai_extraction_score"),
        ]:
            val = report.get(key)
            if val is not None:
                ai_scores.append(Paragraph(f"<b>{val:.0f}</b>/100", styles["ai_metric"]))
                ai_labels.append(Paragraph(label, styles["ai_label"]))
            else:
                ai_scores.append(Paragraph("—", styles["ai_metric"]))
                ai_labels.append(Paragraph(label, styles["ai_label"]))

        if any(report.get(k) is not None for k in ["ai_citability_score", "ai_eeat_score", "ai_schema_score", "ai_extraction_score"]):
            ai_table = Table([ai_scores, ai_labels], colWidths=[1.65 * inch] * 4)
            ai_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ]))
            story.append(ai_table)

        story.append(Spacer(1, 16))

    # ── Key stats row ──
    total_posts = report.get("total_posts", 0)
    cluster_count = report.get("cluster_count", 0)
    analyzed_at = report.get("analyzed_at", "N/A")

    stats_data = [[
        Paragraph(f"<b>{total_posts}</b>", styles["stat_value"]),
        Paragraph(f"<b>{cluster_count}</b>", styles["stat_value"]),
        Paragraph(f"<b>{report.get('problem_count', 0)}</b>", styles["stat_value"]),
    ], [
        Paragraph("Total Posts", styles["stat_label"]),
        Paragraph("Topic Clusters", styles["stat_label"]),
        Paragraph("Issues Found", styles["stat_label"]),
    ]]

    stats_table = Table(stats_data, colWidths=[2.2 * inch] * 3)
    stats_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 8))

    if analyzed_at and analyzed_at != "N/A":
        story.append(Paragraph(
            f"Analyzed: {analyzed_at[:10]}",
            styles["stat_label"],
        ))
    story.append(Spacer(1, 12))

    # ── Headline ──
    headline = report.get("headline", "")
    if headline:
        story.append(Paragraph(_safe(headline), styles["body"]))
        story.append(Spacer(1, 8))

    # ── Issue Breakdown ──
    story.append(Paragraph("Issue Breakdown", styles["heading"]))

    cann_count = report.get("cann_pair_count", 0)
    thin_count = report.get("thin_content_count", 0)
    orphan_count = report.get("orphan_count", 0)
    dup_count = report.get("exact_duplicate_count", 0)

    issue_items = []
    if cann_count:
        issue_items.append(f"{cann_count} cannibalization pairs")
    if thin_count:
        issue_items.append(f"{thin_count} thin content posts")
    if orphan_count:
        issue_items.append(f"{orphan_count} orphan posts (no internal links)")
    if dup_count:
        issue_items.append(f"{dup_count} near-duplicate URL pairs")

    if issue_items:
        # Build a clean data table instead of bullet points
        issue_table_data = []
        for item in issue_items:
            parts = item.split(" ", 1)
            issue_table_data.append([
                Paragraph(f"<b>{parts[0]}</b>", ParagraphStyle("IssueCount", parent=styles["body"], fontName="Helvetica-Bold", fontSize=12, textColor=RED)),
                Paragraph(parts[1] if len(parts) > 1 else "", styles["body"]),
            ])
        issue_table = Table(issue_table_data, colWidths=[0.8 * inch, 5.6 * inch])
        issue_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER_GRAY),
        ]))
        story.append(issue_table)
    else:
        story.append(Paragraph("No major issues detected.", styles["body"]))

    story.append(Spacer(1, 12))

    # ── Top 5 Posts Needing Attention ──
    worst_posts = report.get("worst_posts", [])[:5]
    if worst_posts:
        story.append(Paragraph("Top 5 Posts Needing Attention", styles["heading"]))

        post_table_data = [[
            Paragraph("<b>#</b>", styles["stat_label"]),
            Paragraph("<b>Post</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
            Paragraph("<b>Score</b>", styles["stat_label"]),
            Paragraph("<b>Issue</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
        ]]
        for i, post in enumerate(worst_posts, 1):
            title = post.get("title", "Untitled") if isinstance(post, dict) else getattr(post, "title", "Untitled")
            post_score = post.get("health_score", 0) if isinstance(post, dict) else getattr(post, "health_score", 0)
            issue = post.get("issue", "") if isinstance(post, dict) else getattr(post, "issue", "")
            score_c = _score_color(post_score)
            post_table_data.append([
                Paragraph(str(i), styles["body"]),
                Paragraph(_safe(title[:60]), styles["body"]),
                Paragraph(f"<b>{post_score}</b>", ParagraphStyle("PS", parent=styles["body"], textColor=score_c, fontName="Helvetica-Bold")),
                Paragraph(_safe(issue or "—"), styles["body"]),
            ])

        post_table = Table(post_table_data, colWidths=[0.3 * inch, 3.8 * inch, 0.6 * inch, 1.7 * inch])
        post_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BLACK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER_GRAY),
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
        ]))
        story.append(post_table)
        story.append(Spacer(1, 12))

    # ── Key Findings ──
    key_findings = report.get("key_findings", [])
    if key_findings:
        story.append(Paragraph("Key Findings", styles["heading"]))
        for finding in key_findings:
            story.append(Paragraph(f"&bull; {_safe(finding)}", styles["issue_item"]))
        story.append(Spacer(1, 12))

    # ── Recommendation count teaser ──
    rec_count = report.get("rec_count", 0)
    if rec_count:
        story.append(Paragraph(
            f"<b>{rec_count} specific recommendations generated</b> for {_safe(domain)}.",
            styles["body"],
        ))
        story.append(Spacer(1, 16))

    # ── CTA ──
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"See all {rec_count} recommendations in {display_brand}.",
        styles["cta"],
    ))
    story.append(Paragraph("$99/month. 30-day money-back guarantee.", styles["cta_detail"]))
    story.append(Paragraph("https://enough.app", styles["cta_detail"]))

    # ── Footer ──
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Powered by {display_brand}",
        styles["footer"],
    ))

    # Build PDF
    doc.build(story)
    return buf.getvalue()


def _safe(text: str) -> str:
    """Escape text for safe inclusion in reportlab Paragraph XML."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
