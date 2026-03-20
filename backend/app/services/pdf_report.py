"""PDF audit report generation using reportlab."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io


# ── Brand colors ──
DARK_BG = HexColor("#0a0f1a")
GREEN = HexColor("#22c55e")
WHITE = HexColor("#ffffff")
LIGHT_GRAY = HexColor("#e2e8f0")
MID_GRAY = HexColor("#94a3b8")
DARK_CARD = HexColor("#111827")
BORDER = HexColor("#1f2937")
RED = HexColor("#ef4444")
ORANGE = HexColor("#f97316")
YELLOW = HexColor("#eab308")


def _score_color(score: int) -> HexColor:
    """Return color based on health score value."""
    if score >= 65:
        return GREEN
    if score >= 40:
        return YELLOW
    return RED


def _build_styles() -> dict:
    """Create custom paragraph styles for the PDF."""
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "BrandTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        textColor=GREEN,
        spaceAfter=6,
        alignment=1,  # center
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
        fontSize=16,
        textColor=WHITE,
        spaceBefore=18,
        spaceAfter=10,
    )

    styles["body"] = ParagraphStyle(
        "BodyText",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=LIGHT_GRAY,
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
        fontSize=22,
        textColor=WHITE,
        alignment=1,
    )

    styles["score_big"] = ParagraphStyle(
        "ScoreBig",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=48,
        alignment=1,
        spaceAfter=4,
    )

    styles["issue_item"] = ParagraphStyle(
        "IssueItem",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=LIGHT_GRAY,
        leftIndent=12,
        spaceAfter=4,
        leading=14,
    )

    styles["cta"] = ParagraphStyle(
        "CTA",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=GREEN,
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

    return styles


def generate_audit_pdf(report: dict) -> bytes:
    """Generate a PDF audit report and return raw bytes.

    Args:
        report: Dict with keys matching AuditReport model fields:
            site_name, site_domain, total_posts, analyzed_at, overall_health,
            cluster_count, problem_count, rec_count, cann_pair_count,
            orphan_count, thin_content_count, exact_duplicate_count,
            top_clusters, top_cann_pairs, worst_posts, key_findings, headline

    Returns:
        PDF bytes (io.BytesIO contents).
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

    # ── Dark header with branding ──
    story.append(Paragraph("ENOUGH", styles["title"]))
    story.append(Paragraph(
        f"Content Audit Report &mdash; {report.get('site_domain', '')}",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 12))

    # ── Health score: large prominent number ──
    score = int(report.get("overall_health", 0))
    score_style = ParagraphStyle(
        "ScoreDynamic",
        parent=styles["score_big"],
        textColor=_score_color(score),
    )
    story.append(Paragraph(f"{score}/100", score_style))
    story.append(Paragraph("Blog Health Score", styles["stat_label"]))
    story.append(Spacer(1, 16))

    # ── Key stats row ──
    total_posts = report.get("total_posts", 0)
    analyzed_at = report.get("analyzed_at", "N/A")
    cluster_count = report.get("cluster_count", 0)

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
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 8))

    if analyzed_at and analyzed_at != "N/A":
        story.append(Paragraph(
            f"Analyzed: {analyzed_at[:10]}",
            styles["stat_label"],
        ))
    story.append(Spacer(1, 16))

    # ── Headline ──
    headline = report.get("headline", "")
    if headline:
        story.append(Paragraph(headline, styles["body"]))
        story.append(Spacer(1, 8))

    # ── Issue Breakdown by Category ──
    story.append(Paragraph("Issue Breakdown", styles["heading"]))

    cann_count = report.get("cann_pair_count", 0)
    thin_count = report.get("thin_content_count", 0)
    orphan_count = report.get("orphan_count", 0)
    dup_count = report.get("exact_duplicate_count", 0)
    problem_count = report.get("problem_count", 0)

    issue_items = []
    if cann_count:
        issue_items.append(f"{cann_count} cannibalization pairs")
    if thin_count:
        issue_items.append(f"{thin_count} thin content posts")
    if orphan_count:
        issue_items.append(f"{orphan_count} orphan posts (no internal links)")
    if dup_count:
        issue_items.append(f"{dup_count} near-duplicate URL pairs")
    # Add generic problem count if there are issues not covered above
    other = problem_count - (thin_count + orphan_count)
    if other > 0 and not issue_items:
        issue_items.append(f"{problem_count} total issues detected")

    if issue_items:
        for item in issue_items:
            story.append(Paragraph(f"&bull; {item}", styles["issue_item"]))
    else:
        story.append(Paragraph("No major issues detected.", styles["body"]))

    story.append(Spacer(1, 12))

    # ── Top 5 Issues (worst posts with specific titles) ──
    worst_posts = report.get("worst_posts", [])[:5]
    if worst_posts:
        story.append(Paragraph("Top 5 Posts Needing Attention", styles["heading"]))

        for i, post in enumerate(worst_posts, 1):
            title = post.get("title", "Untitled") if isinstance(post, dict) else getattr(post, "title", "Untitled")
            post_score = post.get("health_score", 0) if isinstance(post, dict) else getattr(post, "health_score", 0)
            issue = post.get("issue", None) if isinstance(post, dict) else getattr(post, "issue", None)
            issue_text = f" &mdash; {issue}" if issue else ""
            story.append(Paragraph(
                f"{i}. <b>{_safe(title)}</b> (score: {post_score}){issue_text}",
                styles["issue_item"],
            ))

        story.append(Spacer(1, 12))

    # ── Key Findings ──
    key_findings = report.get("key_findings", [])
    if key_findings:
        story.append(Paragraph("Key Findings", styles["heading"]))
        for finding in key_findings:
            story.append(Paragraph(f"&bull; {_safe(finding)}", styles["issue_item"]))
        story.append(Spacer(1, 12))

    # ── Recommendation count ──
    rec_count = report.get("rec_count", 0)
    if rec_count:
        story.append(Paragraph(
            f"<b>{rec_count} specific recommendations generated</b> for your blog.",
            styles["body"],
        ))
        story.append(Spacer(1, 16))

    # ── CTA page ──
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Subscribe to Enough to see all {rec_count} recommendations.",
        styles["cta"],
    ))
    story.append(Paragraph("$99/month. 30-day money-back guarantee.", styles["cta_detail"]))
    story.append(Paragraph("https://enough.app/pricing", styles["cta_detail"]))

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
