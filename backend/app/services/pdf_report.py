"""PDF audit report generation using reportlab.

White-label ready: clean white background, professional layout suitable
for agency client decks. Supports optional brand_name and logo_url params
for Scale plan white-labeling.
"""
import io
from datetime import date

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.spider import SpiderChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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

    styles["cover_domain"] = ParagraphStyle(
        "CoverDomain",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=36,
        textColor=BLACK,
        alignment=1,
        spaceAfter=8,
    )

    styles["cover_subtitle"] = ParagraphStyle(
        "CoverSubtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=14,
        textColor=MID_GRAY,
        alignment=1,
        spaceAfter=6,
    )

    styles["cover_date"] = ParagraphStyle(
        "CoverDate",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=MID_GRAY,
        alignment=1,
        spaceAfter=30,
    )

    styles["exec_summary"] = ParagraphStyle(
        "ExecSummary",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=DARK_GRAY,
        spaceAfter=8,
        leading=16,
        leftIndent=12,
        rightIndent=12,
    )

    styles["quick_win_title"] = ParagraphStyle(
        "QuickWinTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=BLACK,
        spaceAfter=2,
        leftIndent=12,
    )

    styles["quick_win_body"] = ParagraphStyle(
        "QuickWinBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=DARK_GRAY,
        spaceAfter=8,
        leading=14,
        leftIndent=12,
    )

    return styles


def _page_footer(canvas, doc, display_brand: str, report_date: str) -> None:
    """Draw page number and branding footer on every page."""
    canvas.saveState()
    page_num = canvas.getPageNumber()
    footer_text = f"Generated by {display_brand}  |  {report_date}  |  Page {page_num}"
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MID_GRAY)
    width, _ = letter
    canvas.drawCentredString(width / 2, 0.35 * inch, footer_text)
    canvas.restoreState()


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
        bottomMargin=0.75 * inch,
    )

    styles = _build_styles()
    story: list = []

    display_brand = brand_name or "Enough"
    domain = report.get("site_domain", "")
    report_date = date.today().strftime("%B %d, %Y")
    score = int(report.get("overall_health", 0))

    # ══════════════════════════════════════════════════════════════
    # COVER PAGE
    # ══════════════════════════════════════════════════════════════
    story.append(Spacer(1, 1.8 * inch))

    # Domain name in large type
    story.append(Paragraph(_safe(domain), styles["cover_domain"]))

    # Subtitle
    story.append(Paragraph("Content Audit Report", styles["cover_subtitle"]))

    # Date stamp
    story.append(Paragraph(report_date, styles["cover_date"]))

    story.append(Spacer(1, 0.5 * inch))

    # Health score as big colored number
    score_style = ParagraphStyle(
        "ScoreDynamic",
        parent=styles["score_big"],
        textColor=_score_color(score),
        fontSize=60,
    )
    story.append(Paragraph(f"{score}/100", score_style))
    story.append(Paragraph("Content Health Score", styles["stat_label"]))

    # Score confidence indicator
    confidence = report.get("score_confidence", "crawl_only")
    if confidence == "crawl_only":
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "Based on content analysis — connect Google Analytics for a complete score",
            ParagraphStyle("Confidence", parent=styles["footer"], fontSize=8, textColor=MID_GRAY),
        ))

    story.append(Spacer(1, 0.5 * inch))

    # Branding on cover
    story.append(Paragraph(
        f"Powered by {_safe(display_brand)}",
        styles["footer"],
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════
    story.append(Paragraph("Executive Summary", styles["heading"]))

    cann_count = report.get("cann_pair_count", 0)
    cann_post_count = report.get("cann_post_count", 0)
    thin_count = report.get("thin_content_count", 0)
    orphan_count = report.get("orphan_count", 0)
    dup_count = report.get("exact_duplicate_count", 0)
    problem_count_val = report.get("problem_count", 0)
    total_posts = report.get("total_posts", 0)

    if score >= 65:
        health_desc = "in good shape"
    elif score >= 40:
        health_desc = "showing moderate issues that need attention"
    else:
        health_desc = "in critical condition and requires immediate action"

    summary_line_1 = (
        f"Your site <b>{_safe(domain)}</b> scored <b>{score}/100</b> on content health, "
        f"meaning your content ecosystem is {health_desc}."
    )

    # Build issue summary parts — separate content problems from cannibalization
    issue_parts: list[str] = []
    if thin_count:
        issue_parts.append(f"{thin_count} thin-content pages")
    if orphan_count:
        issue_parts.append(f"{orphan_count} orphan posts")
    if dup_count:
        issue_parts.append(f"{dup_count} near-duplicate pairs")

    if cann_count > 0 and issue_parts:
        cann_label = f"{cann_post_count} of your {total_posts} posts" if cann_post_count else f"{cann_count} pairs of posts"
        summary_line_2 = (
            f"We found <b>{problem_count_val} content issues</b> ({', '.join(issue_parts)}) "
            f"and <b>{cann_count} cannibalization pairs</b> where {cann_label} have significant content overlap."
        )
    elif cann_count > 0:
        cann_label = f"{cann_post_count} of your {total_posts} posts" if cann_post_count else f"{cann_count} pairs of posts"
        summary_line_2 = (
            f"We found <b>{cann_count} cannibalization pairs</b> where {cann_label} "
            f"have significant content overlap."
        )
    elif issue_parts:
        summary_line_2 = f"We found <b>{problem_count_val} content issues</b>: {', '.join(issue_parts)}."
    else:
        summary_line_2 = "No major content issues detected."
    story.append(Paragraph(summary_line_1, styles["exec_summary"]))
    story.append(Paragraph(summary_line_2, styles["exec_summary"]))
    story.append(Spacer(1, 16))

    # ── Key stats row ──
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

    if analyzed_at and analyzed_at not in ("N/A", "None", "none", "null"):
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

    # ══════════════════════════════════════════════════════════════
    # ISSUE BREAKDOWN (table + bar chart)
    # ══════════════════════════════════════════════════════════════
    story.append(Paragraph("Issue Breakdown", styles["heading"]))

    # Content problems (individual post issues)
    content_issues: list[tuple[str, int]] = []
    if thin_count:
        content_issues.append(("thin content posts", thin_count))
    if orphan_count:
        content_issues.append(("orphan posts (no internal links)", orphan_count))
    if dup_count:
        content_issues.append(("near-duplicate URL pairs", dup_count))

    # SEO issues from problem_count minus the ones we already listed
    seo_other = problem_count_val - thin_count - orphan_count - dup_count
    if seo_other > 0:
        content_issues.append(("SEO issues (title length, missing meta)", seo_other))

    if content_issues or cann_count:
        issue_table_data = []
        for label, count in content_issues:
            issue_table_data.append([
                Paragraph(
                    f"<b>{count}</b>",
                    ParagraphStyle(
                        "IssueCount", parent=styles["body"],
                        fontName="Helvetica-Bold", fontSize=12, textColor=RED,
                    ),
                ),
                Paragraph(label, styles["body"]),
            ])

        # Cannibalization as a separate, clearly labeled row
        if cann_count:
            cann_display = (
                f"cannibalization pairs — {cann_post_count} posts with significant content overlap"
                if cann_post_count
                else "cannibalization pairs detected"
            )
            issue_table_data.append([
                Paragraph(
                    f"<b>{cann_count}</b>",
                    ParagraphStyle(
                        "IssueCountCann", parent=styles["body"],
                        fontName="Helvetica-Bold", fontSize=12, textColor=YELLOW,
                    ),
                ),
                Paragraph(cann_display, styles["body"]),
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

    # ── Bar chart: Posts affected by issue type (not raw pair counts) ──
    # Use cann_post_count (posts involved) instead of cann_count (pairs) for fair comparison
    bar_cann = cann_post_count if cann_post_count else cann_count
    bar_values = [bar_cann, thin_count, orphan_count, dup_count]
    bar_labels = [
        f"Cannibalized\n({bar_cann} posts)", "Thin Content", "Orphan Posts", "Duplicates",
    ]
    if any(v > 0 for v in bar_values):
        story.append(Spacer(1, 12))
        drawing = Drawing(460, 200)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 30
        bc.width = 360
        bc.height = 140
        bc.data = [bar_values]
        bc.categoryAxis.categoryNames = bar_labels
        bc.categoryAxis.labels.fontName = "Helvetica"
        bc.categoryAxis.labels.fontSize = 8
        bc.categoryAxis.labels.angle = 0
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(bar_values) * 1.2 if max(bar_values) > 0 else 10
        bc.valueAxis.valueStep = max(1, int(max(bar_values) * 1.2 / 5)) if max(bar_values) > 0 else 2
        bc.valueAxis.labels.fontName = "Helvetica"
        bc.valueAxis.labels.fontSize = 8
        bc.bars[0].fillColor = HexColor("#ef4444")
        bc.bars[0].strokeColor = HexColor("#dc2626")
        bc.bars[0].strokeWidth = 0.5
        bc.barWidth = 40
        drawing.add(bc)
        story.append(drawing)

    story.append(Spacer(1, 12))

    # ══════════════════════════════════════════════════════════════
    # TOPIC CLUSTERS
    # ══════════════════════════════════════════════════════════════
    top_clusters = report.get("top_clusters", [])
    if top_clusters:
        story.append(Paragraph("Topic Clusters", styles["heading"]))
        story.append(Paragraph(
            f"Your content organizes into {cluster_count} topic clusters. "
            f"Each cluster groups semantically similar posts.",
            styles["body"],
        ))
        story.append(Spacer(1, 8))

        cluster_table_data = [[
            Paragraph("<b>Cluster</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
            Paragraph("<b>Posts</b>", styles["stat_label"]),
            Paragraph("<b>Health</b>", styles["stat_label"]),
            Paragraph("<b>State</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
        ]]
        for cl in top_clusters:
            cl_health = cl.get("health_score", 0)
            cl_color = _score_color(cl_health)
            cluster_table_data.append([
                Paragraph(_safe(cl.get("label", "Unnamed")[:35]), styles["body"]),
                Paragraph(str(cl.get("post_count", 0)), ParagraphStyle("C", parent=styles["body"], alignment=1)),
                Paragraph(
                    f"<b>{cl_health}</b>",
                    ParagraphStyle("CS", parent=styles["body"], textColor=cl_color,
                                   fontName="Helvetica-Bold", alignment=1),
                ),
                Paragraph(_safe(cl.get("ecosystem_state", "unknown")), styles["body"]),
            ])

        cluster_table = Table(cluster_table_data, colWidths=[2.8 * inch, 0.6 * inch, 0.7 * inch, 1.2 * inch])
        cluster_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BLACK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER_GRAY),
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
        ]))
        story.append(cluster_table)
        story.append(Spacer(1, 12))

    # ══════════════════════════════════════════════════════════════
    # AI READINESS (table + spider chart)
    # ══════════════════════════════════════════════════════════════
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
            if ai_pct_ready < 50:
                ai_msg = f"Only {ai_pct_ready:.0f}% of your posts are structured for AI citation."
            else:
                ai_msg = f"{ai_pct_ready:.0f}% of your posts are structured for AI citation."
            story.append(Paragraph(ai_msg, ai_headline_style))
            story.append(Spacer(1, 8))

        # AI scores row (numeric table)
        ai_score_keys = [
            ("AI Citability", "ai_citability_score"),
            ("E-E-A-T", "ai_eeat_score"),
            ("Schema", "ai_schema_score"),
            ("Extraction", "ai_extraction_score"),
        ]
        ai_scores = []
        ai_labels = []
        for label, key in ai_score_keys:
            val = report.get(key)
            if val is not None:
                ai_scores.append(Paragraph(f"<b>{val:.0f}</b>/100", styles["ai_metric"]))
            else:
                ai_scores.append(Paragraph("---", styles["ai_metric"]))
            ai_labels.append(Paragraph(label, styles["ai_label"]))

        has_ai_data = any(
            report.get(k) is not None
            for k in ["ai_citability_score", "ai_eeat_score", "ai_schema_score", "ai_extraction_score"]
        )
        if has_ai_data:
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
            story.append(Spacer(1, 12))

            # ── Spider/radar chart for AI readiness scores ──
            spider_data = [
                float(report.get("ai_citability_score") or 0),
                float(report.get("ai_eeat_score") or 0),
                float(report.get("ai_schema_score") or 0),
                float(report.get("ai_extraction_score") or 0),
            ]
            if any(v > 0 for v in spider_data):
                spider_drawing = Drawing(320, 240)
                spider = SpiderChart()
                spider.x = 60
                spider.y = 20
                spider.width = 200
                spider.height = 200
                spider.data = [spider_data]
                spider.labels = ["Citability", "E-E-A-T", "Schema", "Extraction"]
                spider.strands[0].fillColor = Color(0.145, 0.388, 0.922, 0.2)
                spider.strands[0].strokeColor = BLUE
                spider.strands[0].strokeWidth = 2
                spider_drawing.add(spider)
                story.append(spider_drawing)

        # ── E-E-A-T critical warning ──
        ai_eeat_val = report.get("ai_eeat_score")
        if ai_eeat_val is not None and ai_eeat_val < 20:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                "Your site has no visible author information, no publication dates, "
                "and no author credentials. These are the signals AI systems use to "
                "determine whether to cite your content.",
                ParagraphStyle("EEATWarn", parent=styles["body"],
                               textColor=RED, fontName="Helvetica-Bold"),
            ))
            story.append(Spacer(1, 8))

        # ── GEO-specific issue summary (GEO-4) ──
        geo_issues = []
        pct_schema = report.get("ai_pct_schema", 0) or 0
        if pct_schema < 50:
            geo_issues.append(f"{100 - pct_schema:.0f}% of your posts have no schema markup")
        q_ratio = report.get("avg_question_header_ratio", 0) or 0
        if q_ratio < 0.3:
            geo_issues.append(f"Only {q_ratio * 100:.0f}% of H2 headers are question-format (target: 30%)")
        data_density = report.get("avg_data_density", 0) or 0
        if data_density < 1.0:
            geo_issues.append(f"Average data density: {data_density:.1f} per 200 words (target: 1.0)")
        faq_pct = report.get("pct_has_faq", 0) or 0
        if faq_pct < 30:
            geo_issues.append(f"Only {faq_pct:.0f}% of posts have FAQ sections")

        if geo_issues:
            story.append(Spacer(1, 8))
            story.append(Paragraph("Why AI systems skip your content:", styles["heading"]))
            for issue in geo_issues[:3]:
                story.append(Paragraph(f"\u2022 {_safe(issue)}", styles["body"]))
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                "Google AI Overviews now appear on ~50% of searches. "
                "Organic CTR drops 34.5% when AI Overviews are present. "
                "Subscribe to see exactly which posts to fix and get AI-ready recommendations.",
                ParagraphStyle("GEOCTA", parent=styles["body"], textColor=YELLOW, fontName="Helvetica-Bold"),
            ))

        story.append(Spacer(1, 16))

    # ══════════════════════════════════════════════════════════════
    # TOP 3 QUICK WINS
    # ══════════════════════════════════════════════════════════════
    quick_wins: list[dict] = []

    # If schema score is 0, that's the highest-impact quick win
    ai_schema_val = report.get("ai_schema_score")
    if ai_schema_val is not None and ai_schema_val == 0:
        quick_wins.append({
            "title": "Add structured data (schema markup) to your top posts",
            "body": (
                "None of your posts have JSON-LD schema markup. "
                "Adding Article/BlogPosting schema directly enables "
                "rich results in Google and increases AI citation rates. "
                "Start with your 10 highest-traffic posts."
            ),
        })

    # Add top cann pair as a specific, actionable win
    top_cann = report.get("top_cann_pairs", [])
    if top_cann and len(top_cann) > 0:
        pair = top_cann[0]
        a_title = pair.get("post_a_title", "")[:55]
        b_title = pair.get("post_b_title", "")[:55]
        sim = pair.get("overlap_score", 0)
        quick_wins.append({
            "title": f"Consolidate or differentiate: \"{a_title}\" vs \"{b_title}\"",
            "body": (
                f"These posts are {sim*100:.0f}% similar and may dilute each other's search visibility. "
                f"Either merge them into one definitive post or rewrite each to target distinct keywords."
            ),
        })

    # Fill remaining slots from recommendations — prefer optimize (quick SEO fixes) over expand
    recommendations = report.get("top_recs") or report.get("recommendations", [])
    # Sort: optimize first (15-min fixes), then expand (content work), skip differentiate
    non_diff_recs = [
        r for r in recommendations
        if isinstance(r, dict) and r.get("rec_type") != "differentiate"
    ]
    non_diff_recs.sort(key=lambda r: (0 if r.get("rec_type") == "optimize" else 1))

    # Skip recs targeting the same posts as the Quick Win #2 cann pair
    cann_pair_titles: set[str] = set()
    if top_cann:
        cann_pair_titles.add(top_cann[0].get("post_a_title", ""))
        cann_pair_titles.add(top_cann[0].get("post_b_title", ""))

    seen_titles: set[str] = set()
    for rec in non_diff_recs:
        if len(quick_wins) >= 3:
            break
        rec_title = rec.get("title", "")
        post_title = rec.get("post_title", "")
        if post_title in seen_titles or post_title in cann_pair_titles:
            continue
        seen_titles.add(post_title)
        quick_wins.append({
            "title": _safe(rec_title),
            "body": _safe(rec.get("summary", "") or ""),
        })

    if quick_wins:
        story.append(Paragraph("Top 3 Quick Wins", styles["heading"]))
        for idx, win in enumerate(quick_wins[:3], 1):
            story.append(Paragraph(f"{idx}. {win['title']}", styles["quick_win_title"]))
            if win.get("body"):
                story.append(Paragraph(win["body"], styles["quick_win_body"]))
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
            raw_issue = post.get("issue", "") if isinstance(post, dict) else getattr(post, "issue", "")
            issue = _humanize_issues(raw_issue, title) if raw_issue else "low health score"
            score_c = _score_color(post_score)
            post_table_data.append([
                Paragraph(str(i), styles["body"]),
                Paragraph(_safe(title[:60]), styles["body"]),
                Paragraph(
                    f"<b>{post_score}</b>",
                    ParagraphStyle(
                        "PS", parent=styles["body"],
                        textColor=score_c, fontName="Helvetica-Bold",
                    ),
                ),
                Paragraph(_safe(issue), styles["body"]),
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

    # ── Recommendation count teaser + example ──
    rec_count = report.get("rec_count", 0)
    if rec_count:
        story.append(Paragraph(
            f"<b>{rec_count} specific recommendations generated</b> for {_safe(domain)}.",
            styles["body"],
        ))

        # Show one concrete recommendation example — pick the most impressive one
        sample_recs = report.get("top_recs") or report.get("recommendations", [])
        if sample_recs:
            # Prefer a rec that names a specific post and has a concrete summary
            sample = None
            for sr in sample_recs:
                if not isinstance(sr, dict):
                    continue
                # Skip expand recs (often about low-value posts)
                if sr.get("rec_type") == "expand":
                    continue
                sample = sr
                break
            if not sample and sample_recs:
                sample = sample_recs[0] if isinstance(sample_recs[0], dict) else None

            if sample:
                rec_title = sample.get("title", "")
                post_title_val = sample.get("post_title", "")
                summary_val = sample.get("summary", "") or ""
                # Don't repeat post name if it's already in the rec title
                if post_title_val and post_title_val not in rec_title:
                    display_title = f"{_safe(rec_title[:70])} — {_safe(post_title_val[:40])}"
                else:
                    display_title = _safe(rec_title[:80])
                if display_title:
                    story.append(Spacer(1, 8))
                    story.append(Paragraph("Example recommendation:", styles["stat_label"]))
                    story.append(Paragraph(
                        f"<b>{display_title}</b>",
                        ParagraphStyle("ExampleRec", parent=styles["body"],
                                       leftIndent=12, rightIndent=12, textColor=DARK_GRAY),
                    ))
                    if summary_val:
                        story.append(Paragraph(
                            f"<i>{_safe(summary_val[:180])}</i>",
                            ParagraphStyle("ExampleRecBody", parent=styles["body"],
                                           leftIndent=12, rightIndent=12, fontSize=9, textColor=MID_GRAY),
                        ))

        story.append(Spacer(1, 8))

    # ── Top Cannibalization Pairs (fills final page before CTA) ──
    top_cann_data = report.get("top_cann_pairs", [])
    if top_cann_data and len(top_cann_data) >= 3:
        story.append(Paragraph("Top Cannibalization Pairs", styles["heading"]))
        story.append(Paragraph(
            "These post pairs have significant content overlap. Consider merging or differentiating them.",
            styles["body"],
        ))
        story.append(Spacer(1, 6))

        cann_table_data = [[
            Paragraph("<b>Post A</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
            Paragraph("<b>Post B</b>", ParagraphStyle("TH", parent=styles["stat_label"], alignment=0)),
            Paragraph("<b>Similarity</b>", styles["stat_label"]),
        ]]
        for cp in top_cann_data[:6]:
            sim = cp.get("overlap_score", 0)
            sim_color = RED if sim >= 0.85 else YELLOW
            a_title = cp.get("post_a_title", "")
            b_title = cp.get("post_b_title", "")
            # When titles are identical, add URL slug to distinguish
            if a_title == b_title:
                a_slug = cp.get("post_a_url", "").rstrip("/").split("/")[-1]
                b_slug = cp.get("post_b_url", "").rstrip("/").split("/")[-1]
                if a_slug != b_slug:
                    a_title = f"{a_title} (/{a_slug})"
                    b_title = f"{b_title} (/{b_slug})"
            cann_table_data.append([
                Paragraph(_safe(_truncate(a_title, 45)), styles["body"]),
                Paragraph(_safe(_truncate(b_title, 45)), styles["body"]),
                Paragraph(
                    f"<b>{sim*100:.0f}%</b>",
                    ParagraphStyle("SimPct", parent=styles["body"],
                                   textColor=sim_color, fontName="Helvetica-Bold", alignment=1),
                ),
            ])
        cann_table = Table(cann_table_data, colWidths=[2.6 * inch, 2.6 * inch, 0.9 * inch])
        cann_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BLACK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER_GRAY),
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
        ]))
        story.append(cann_table)
        story.append(Spacer(1, 12))

    # ── CTA (keep together so it doesn't split across pages) ──
    cta_elements: list = [Spacer(1, 8)]
    cta_elements.append(Paragraph(
        f"Get all {rec_count} recommendations in {display_brand}.",
        styles["cta"],
    ))
    ai_schema_cta = report.get("ai_schema_score")
    if ai_schema_cta is not None and ai_schema_cta == 0:
        cta_elements.append(Paragraph(
            "Every day without structured data, AI systems cite your competitors instead of you.",
            ParagraphStyle("CtaUrgency", parent=styles["cta_detail"],
                           fontName="Helvetica-Bold", textColor=YELLOW),
        ))
    cta_elements.append(Paragraph("$149/month. 30-day money-back guarantee.", styles["cta_detail"]))
    cta_elements.append(Paragraph("https://enough.app", styles["cta_detail"]))
    story.append(KeepTogether(cta_elements))

    # ── Build PDF with page footer template ──
    def _on_first_page(canvas, doc_ref):
        """Cover page footer -- minimal, just branding."""
        _page_footer(canvas, doc_ref, display_brand, report_date)

    def _on_later_pages(canvas, doc_ref):
        """Content pages footer with page number."""
        _page_footer(canvas, doc_ref, display_brand, report_date)

    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_later_pages)
    return buf.getvalue()


_ISSUE_LABELS = {
    # SEO basics
    "seo_missing_meta": "Missing meta description",
    "seo_title_length": "Title too short/long",
    "seo_no_headings": "No headings",
    "seo_no_internal_links": "No internal links",
    "seo_no_images": "No images",
    # Content quality
    "thin_content": "Thin content",
    "thin_below_cluster_avg": "Thin content",
    "thin_high_bounce": "Thin content (high bounce)",
    "readability_too_complex": "Hard to read",
    # Structure
    "orphan": "No inbound links",
    "missing_schema": "No schema markup",
    "cannibalization": "Cannibalizing another post",
    # Decay
    "decay_mild": "Mild traffic decline",
    "decay_moderate": "Moderate traffic decline",
    "decay_severe": "Severe traffic decline",
    # AI / GEO readiness
    "low_ai_citability": "Low AI citability",
    "weak_eeat": "Weak E-E-A-T signals",
    "poor_ai_structure": "Poor AI structure",
    "geo_no_faq_section": "No FAQ section",
    "geo_no_data_tables": "No data tables",
    "geo_no_experience_markers": "No experience markers",
    "geo_no_question_headers": "No question headers",
    "geo_low_data_density": "Low data density",
    "geo_no_answer_first": "No answer-first structure",
    "geo_missing_faq_schema": "Missing FAQ schema",
    "geo_no_freshness_date": "No freshness date",
    # Pipeline-detected
    "velocity_decline": "Publishing velocity decline",
    "intent_mismatch": "Intent mismatch",
    "serp_opportunity_missed": "Missed SERP opportunity",
}


def _humanize_issues(raw: str, title: str = "") -> str:
    """Convert comma-separated problem_type codes to human-readable labels."""
    parts = [p.strip() for p in raw.split(",")]
    labels = []
    for p in parts:
        if not p:
            continue
        if p == "seo_title_length" and title:
            # Determine direction from actual title length
            labels.append("Title too short" if len(title) < 30 else "Title too long")
        else:
            labels.append(_ISSUE_LABELS.get(p, p.replace("_", " ")))
    # Deduplicate while preserving order
    labels = list(dict.fromkeys(labels))
    return ", ".join(labels) if labels else "low health score"


def _truncate(text: str, max_len: int = 45) -> str:
    """Truncate at word boundary with ellipsis."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "..."


def _safe(text: str) -> str:
    """Escape text for safe inclusion in reportlab Paragraph XML."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
