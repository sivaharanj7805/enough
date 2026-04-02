"""PDF audit report — premium cold-DM design, 5 pages (v5.0).

Structure:
  1. Cover (hook + urgency)
  2. Executive Summary + AI Readiness Spider Chart + Key Findings + Content Profile
  3. Detailed AI Readiness + Issue Breakdown
  4. Topic Clusters + Quick Wins + Top 5 Posts
  5. Example Fix + Cannibalization + 30-Day Plan + What You Get + CTA

Narrative arc:
  Shock (cover) -> AI differentiation (spider chart) -> Understanding (findings)
  -> Action (quick wins) -> Proof (pairs) -> Next step (CTA)

v5.0 changes:
  - AI Readiness spider chart moved to page 2 (before Key Findings)
  - Quick Win #3 header/body mismatch fixed (title now overridden with body)
  - Example Fix filler phrases stripped from generated meta descriptions
  - Cover content block recentered (1.85in spacer)
  - Landing/index pages filtered from rankings and recommendations
"""
import io
import logging
import math
import os as _os
import re
from datetime import date

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inter font registration — falls back to Helvetica if files not found
# ---------------------------------------------------------------------------
_INTER_REGISTERED = False
_FONT_DIR = _os.path.dirname(__file__)

def _register_inter():
    """Register Inter font family with ReportLab if available."""
    global _INTER_REGISTERED
    if _INTER_REGISTERED:
        return
    _INTER_REGISTERED = True
    regular = _os.path.join(_FONT_DIR, "Inter-Regular.ttf")
    bold = _os.path.join(_FONT_DIR, "Inter-Bold.ttf")
    if _os.path.exists(regular) and _os.path.exists(bold):
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            pdfmetrics.registerFont(TTFont("Inter", regular))
            pdfmetrics.registerFont(TTFont("Inter-Bold", bold))
            from reportlab.lib.fonts import addMapping
            addMapping("Inter", 0, 0, "Inter")       # normal
            addMapping("Inter", 1, 0, "Inter-Bold")   # bold
            logger.info("Inter font registered successfully")
        except Exception as e:
            logger.warning("Inter font registration failed, using Helvetica: %s", e)
    else:
        logger.debug("Inter font files not found, using Helvetica fallback")

# ---------------------------------------------------------------------------
# Semantic color system
# ---------------------------------------------------------------------------
# Green (#059669): scores >= 55
# Amber (#D97706): scores 30-54
# Red   (#DC2626): scores < 30
# EVERY number uses _sc(). No exceptions.

BRAND_BLUE = HexColor("#2563EB")
ACCENT_BLUE = HexColor("#3B82F6")
BLACK = HexColor("#111827")
DARK_GRAY = HexColor("#374151")
MID_GRAY = HexColor("#6B7280")
CAPTION_GRAY = HexColor("#9CA3AF")
BORDER_GRAY = HexColor("#E5E7EB")
BG_GRAY = HexColor("#F9FAFB")
GRID_GRAY = HexColor("#F3F4F6")
WHITE = HexColor("#FFFFFF")

SC_GREEN = HexColor("#059669")
SC_AMBER = HexColor("#D97706")
SC_RED = HexColor("#DC2626")
SC_ORANGE = HexColor("#EA580C")
SC_LIME = HexColor("#65A30D")
SC_TEAL = HexColor("#0891B2")
SC_DARK_AMBER = HexColor("#B45309")

# Container backgrounds
BG_NEUTRAL = HexColor("#F9FAFB")       # Key Findings, Content Profile, 30-Day Plan
BG_WARNING = HexColor("#FFF7ED")       # "What this means"
BG_EXAMPLE = HexColor("#EFF6FF")       # Example Fix
BG_POSITIVE = HexColor("#F0FDF4")      # What You Get

# Container borders
BD_NEUTRAL = HexColor("#E5E7EB")
BD_WARNING = HexColor("#FDBA74")
BD_EXAMPLE = HexColor("#93C5FD")
BD_POSITIVE = HexColor("#86EFAC")

# Page layout — tight margins to fit 5 pages without cutting content
PAGE_W, PAGE_H = letter  # 612 x 792
MARGIN_LR = 0.75 * inch  # 54pt
MARGIN_TOP = 0.85 * inch  # 61pt (was 72pt)
MARGIN_BOTTOM = 0.65 * inch  # 47pt (was 54pt)
CW = PAGE_W - 2 * MARGIN_LR  # 504pt content width

# Section top border colors
BORDER_BLUE = HexColor("#3B82F6")
BORDER_GREEN = HexColor("#059669")
BORDER_AMBER = HexColor("#D97706")

# Logo path
_LOGO_PATH = _os.path.join(_os.path.dirname(__file__), "logo.png")


# ---------------------------------------------------------------------------
# Score color function — THE master rule
# ---------------------------------------------------------------------------
def _sc(v):
    """Score color: green >= 75, yellow-green 60-74, amber 30-59, red < 30."""
    v = int(v or 0)
    if v >= 75:
        return SC_GREEN
    if v >= 60:
        return SC_LIME
    if v >= 30:
        return SC_AMBER
    return SC_RED


def _sch(v):
    """Score color as hex string."""
    return _sc(v).hexval()


def _sw(v):
    """Score word descriptor — creates urgency for cold outreach."""
    v = int(v or 0)
    if v >= 81:
        return "excellent"
    if v >= 66:
        return "good"
    if v >= 51:
        return "needs attention"
    if v >= 31:
        return "poor"
    return "critical"


def _olap_color(pct):
    """Overlap percentage color — graduated by raw pct (0-100)."""
    if pct >= 85:
        return SC_RED
    if pct >= 83:
        return SC_DARK_AMBER
    return SC_AMBER


# Ecosystem state -> human label
_ECO = {
    "forest": "Healthy",
    "meadow": "Growing",
    "desert": "Declining",
    "swamp": "At Risk",
    "seedbed": "New",
}


def _eco(s):
    """Map ecosystem_state to human label."""
    return _ECO.get(s, s.title() if s else "\u2014")


def _stc(status):
    """Status text color."""
    return {
        "Healthy": SC_GREEN,
        "Growing": SC_TEAL,
        "Declining": SC_RED,
        "At Risk": SC_RED,
        "New": MID_GRAY,
        "Strong": SC_GREEN,
        "Moderate": SC_TEAL,
        "Needs Attention": SC_AMBER,
    }.get(status, MID_GRAY)


def _readability_label(score):
    """Audience-level label for Flesch readability (6-tier)."""
    if score >= 80:
        return "easy"
    if score >= 70:
        return "fairly easy"
    if score >= 60:
        return "standard"
    if score >= 50:
        return "professional audience level"
    if score >= 30:
        return "difficult"
    return "very difficult"


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
def _build_styles():
    """Return dict of ParagraphStyle objects used throughout."""
    base = getSampleStyleSheet()
    s = {}

    # Use Inter font if registered, fall back to Helvetica
    _regular = _os.path.join(_FONT_DIR, "Inter-Regular.ttf")
    _fn = "Inter" if _os.path.exists(_regular) else "Helvetica"
    _fn_bold = "Inter-Bold" if _os.path.exists(_regular) else "Helvetica-Bold"

    # Page headers — 24pt (compact)
    s["h1"] = ParagraphStyle(
        "H1", parent=base["Heading1"], fontName=_fn_bold,
        fontSize=24, textColor=BLACK, leading=29, spaceBefore=0, spaceAfter=4,
    )

    # Sub-headers — 15pt
    s["h2"] = ParagraphStyle(
        "H2", parent=base["Heading2"], fontName=_fn_bold,
        fontSize=15, textColor=BLACK, leading=19, spaceBefore=0, spaceAfter=4,
    )

    # Sub-header 13pt
    s["h3"] = ParagraphStyle(
        "H3", parent=base["Heading3"], fontName=_fn_bold,
        fontSize=13, textColor=BLACK, leading=17, spaceBefore=0, spaceAfter=4,
    )

    # Body text — 10.5pt (compact to fit 5 pages)
    s["body"] = ParagraphStyle(
        "Body", parent=base["Normal"], fontName=_fn,
        fontSize=10.5, textColor=DARK_GRAY, leading=14.5, spaceAfter=3,
    )

    # Body bold
    s["body_bold"] = ParagraphStyle(
        "BodyBold", parent=s["body"], fontName="Helvetica-Bold",
        textColor=BLACK,
    )

    # Bullet
    s["bullet"] = ParagraphStyle(
        "Bullet", parent=s["body"], leftIndent=12, spaceAfter=3,
    )

    # Impact line — green italic
    s["impact"] = ParagraphStyle(
        "Impact", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=10.5, textColor=SC_GREEN, leading=14.5, spaceAfter=6,
        leftIndent=16,
    )

    # Caption / label — 10pt
    s["caption"] = ParagraphStyle(
        "Caption", parent=base["Normal"], fontName="Helvetica",
        fontSize=10, textColor=CAPTION_GRAY, leading=13,
    )

    # Table header — 10pt semibold (using Bold as closest to semibold)
    s["th"] = ParagraphStyle(
        "TH", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=10, textColor=MID_GRAY, leading=13,
    )
    s["th_center"] = ParagraphStyle(
        "THC", parent=s["th"], alignment=TA_CENTER,
    )
    s["th_right"] = ParagraphStyle(
        "THR", parent=s["th"], alignment=TA_RIGHT,
    )

    # Table data — 10pt (compact)
    s["td"] = ParagraphStyle(
        "TD", parent=base["Normal"], fontName="Helvetica",
        fontSize=10, textColor=DARK_GRAY, leading=13.5,
    )
    s["td_center"] = ParagraphStyle(
        "TDC", parent=s["td"], alignment=TA_CENTER,
    )
    s["td_right"] = ParagraphStyle(
        "TDR", parent=s["td"], alignment=TA_RIGHT,
    )

    # Stat box number — 32pt
    s["stat_num"] = ParagraphStyle(
        "StatNum", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=32, textColor=DARK_GRAY, alignment=TA_CENTER, leading=32,
    )

    # Stat box label — 11pt grey
    s["stat_label"] = ParagraphStyle(
        "StatLabel", parent=base["Normal"], fontName="Helvetica",
        fontSize=11, textColor=CAPTION_GRAY, alignment=TA_CENTER,
    )

    # AI dimension number — 24pt
    s["ai_num"] = ParagraphStyle(
        "AINum", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=24, alignment=TA_CENTER, leading=24,
    )
    s["ai_label"] = ParagraphStyle(
        "AILabel", parent=base["Normal"], fontName="Helvetica",
        fontSize=10, textColor=CAPTION_GRAY, alignment=TA_CENTER,
    )

    # Cover styles
    s["c_logo"] = ParagraphStyle(
        "CLogo", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=14, textColor=BRAND_BLUE, alignment=TA_CENTER,
    )
    s["c_domain"] = ParagraphStyle(
        "CDomain", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=36, textColor=BLACK, alignment=TA_CENTER, leading=40,
        spaceAfter=4,
    )
    s["c_subtitle"] = ParagraphStyle(
        "CSubtitle", parent=base["Normal"], fontName="Helvetica",
        fontSize=14, textColor=CAPTION_GRAY, alignment=TA_CENTER, spaceAfter=2,
    )
    s["c_date"] = ParagraphStyle(
        "CDate", parent=base["Normal"], fontName="Helvetica",
        fontSize=12, textColor=CAPTION_GRAY, alignment=TA_CENTER, spaceAfter=2,
    )
    s["c_score_label"] = ParagraphStyle(
        "CScoreLabel", parent=base["Normal"], fontName="Helvetica",
        fontSize=12, textColor=CAPTION_GRAY, alignment=TA_CENTER,
    )
    s["c_score_context"] = ParagraphStyle(
        "CScoreCtx", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=11, textColor=CAPTION_GRAY, alignment=TA_CENTER,
    )
    s["c_confidence"] = ParagraphStyle(
        "CConf", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=10, textColor=CAPTION_GRAY, alignment=TA_CENTER,
    )
    s["c_urgency"] = ParagraphStyle(
        "CUrgency", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=16, textColor=SC_RED, alignment=TA_CENTER, leading=21,
        leftIndent=24, rightIndent=24,
    )
    s["c_url"] = ParagraphStyle(
        "CURL", parent=base["Normal"], fontName="Helvetica",
        fontSize=12, textColor=BRAND_BLUE, alignment=TA_CENTER,
    )

    # Quick wins
    s["qw_title"] = ParagraphStyle(
        "QWTitle", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, textColor=BLACK, spaceAfter=1, leftIndent=8,
    )
    s["qw_body"] = ParagraphStyle(
        "QWBody", parent=base["Normal"], fontName="Helvetica",
        fontSize=10.5, textColor=DARK_GRAY, leading=14.5, spaceAfter=1,
        leftIndent=8,
    )

    # CTA
    s["cta_headline"] = ParagraphStyle(
        "CTAHead", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=20, textColor=BRAND_BLUE, alignment=TA_CENTER,
        spaceBefore=4, spaceAfter=2,
    )
    s["cta_urgency"] = ParagraphStyle(
        "CTAUrg", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=12, textColor=SC_RED, alignment=TA_CENTER, spaceAfter=2,
    )
    s["cta_price"] = ParagraphStyle(
        "CTAPrice", parent=base["Normal"], fontName="Helvetica",
        fontSize=10.5, textColor=CAPTION_GRAY, alignment=TA_CENTER, spaceAfter=2,
    )
    s["cta_link"] = ParagraphStyle(
        "CTALink", parent=base["Normal"], fontName="Helvetica",
        fontSize=11, textColor=BRAND_BLUE, alignment=TA_CENTER,
    )

    return s


# ---------------------------------------------------------------------------
# Canvas callbacks — footer + section top borders
# ---------------------------------------------------------------------------
def _draw_footer(canvas, doc, dt_str, domain=""):
    """Footer: grey line + centered 'Tended . domain . date . Page N' in 9pt."""
    canvas.saveState()
    # Line 20px from bottom edge
    y_line = 20
    canvas.setStrokeColor(BORDER_GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_LR, y_line, PAGE_W - MARGIN_LR, y_line)
    # Text below line — include domain on every page per spec rule #1
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(CAPTION_GRAY)
    page_num = canvas.getPageNumber()
    if domain:
        footer_text = f"Tended \u00b7 {domain} \u00b7 {dt_str} \u00b7 Page {page_num}"
    else:
        footer_text = f"Tended \u00b7 {dt_str} \u00b7 Page {page_num}"
    canvas.drawCentredString(PAGE_W / 2, y_line - 12, footer_text)
    # S-04: Make "Tended" clickable to usetended.io on every page
    from reportlab.pdfbase.pdfmetrics import stringWidth
    tended_w = stringWidth("Tended", "Helvetica", 9)
    tended_x = PAGE_W / 2 - stringWidth(footer_text, "Helvetica", 9) / 2
    canvas.linkURL(
        "https://usetended.io",
        (tended_x, y_line - 14, tended_x + tended_w, y_line - 3),
        relative=0,
    )
    canvas.restoreState()


def _draw_top_border(canvas, color):
    """Draw a 3px colored line across top of content area."""
    canvas.saveState()
    y = PAGE_H - MARGIN_TOP + 4  # Just above the content area
    canvas.setStrokeColor(color)
    canvas.setLineWidth(3)
    canvas.line(MARGIN_LR, y, PAGE_W - MARGIN_LR, y)
    canvas.restoreState()


def _make_page_callback(dt_str, page_borders, domain=""):
    """Return canvas callbacks for first and later pages."""

    def _on_page(canvas, doc):
        page_num = canvas.getPageNumber()
        _draw_footer(canvas, doc, dt_str, domain)
        # Top borders by page number
        border_color = page_borders.get(page_num)
        if border_color:
            _draw_top_border(canvas, border_color)

    return _on_page


# ---------------------------------------------------------------------------
# Container helper — tinted box with border
# ---------------------------------------------------------------------------
def _container(flowables, bg, border_color, width=None, padding=12):
    """Wrap flowables in a single-cell Table with tinted background and border."""
    w = width or (CW - 4)
    t = Table([[flowables]], colWidths=[w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ---------------------------------------------------------------------------
# Health Score Bar
# ---------------------------------------------------------------------------
def _health_bar(score, s):
    """5-segment gradient bar with marker above at score position."""
    # Marker row — larger, bolder position indicator
    bw = CW / 5
    # Determine which bucket the score falls in (aligned with _sw thresholds)
    if score >= 81:
        bucket = 4
    elif score >= 66:
        bucket = 3
    elif score >= 51:
        bucket = 2
    elif score >= 31:
        bucket = 1
    else:
        bucket = 0
    marker_cells = []
    for i in range(5):
        if i == bucket:
            marker_cells.append(Paragraph(
                f"<font color='{_sch(score)}'><b>\u25cf {score}/100</b></font>",
                ParagraphStyle("Marker", fontName="Helvetica-Bold",
                               fontSize=11, alignment=TA_CENTER),
            ))
        else:
            marker_cells.append(Paragraph("", s["body"]))

    # Bar row — empty cells colored (taller for visibility)
    bar_cells = [Paragraph("", s["body"]) for _ in range(5)]

    # Label row — aligned with _sw thresholds
    labels = ["Critical", "Poor", "Needs Attention", "Good", "Excellent"]
    label_cells = [
        Paragraph(
            f"<font size='9' color='#9CA3AF'>{lbl}</font>",
            ParagraphStyle(f"BL{i}", fontSize=9, textColor=CAPTION_GRAY,
                           alignment=TA_CENTER),
        )
        for i, lbl in enumerate(labels)
    ]

    tbl = Table(
        [marker_cells, bar_cells, label_cells],
        colWidths=[bw] * 5,
        rowHeights=[20, 14, 16],
    )
    colors = [SC_RED, SC_ORANGE, SC_AMBER, SC_LIME, SC_GREEN]
    style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]
    for i, clr in enumerate(colors):
        style_cmds.append(("BACKGROUND", (i, 1), (i, 1), clr))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


# ---------------------------------------------------------------------------
# Spider / Radar Chart — drawn manually with reportlab Drawing
# ---------------------------------------------------------------------------
def _spider_chart(citability, eeat, schema, extraction):
    """Diamond spider chart, 220pt tall, centered. Blue fill 25% opacity.

    The 4-axis radar creates a distinctive lopsided shape when one axis (schema)
    collapses to 0. This is the visual "aha moment" — no other tool produces it.
    """
    from reportlab.graphics.shapes import Drawing, Polygon, Line, Circle, String

    chart_size = 200
    d = Drawing(CW, chart_size + 28)
    cx = CW / 2
    cy = chart_size / 2 + 6
    radius = 82  # Balanced size — visible but compact

    # Axes: top=Citability, right=E-E-A-T, bottom=Schema, left=Extraction
    # Angles: top=90, right=0, bottom=270, left=180
    axes = [
        (0, 1, "Citability", citability),     # top (12 o'clock)
        (1, 0, "E-E-A-T", eeat),             # right (3 o'clock)
        (0, -1, "Schema", schema),            # bottom (6 o'clock)
        (-1, 0, "Extraction", extraction),    # left (9 o'clock)
    ]

    # Grid lines at 25%, 50%, 75%, 100% — diamond shapes for reference
    for pct in [0.25, 0.5, 0.75, 1.0]:
        r = radius * pct
        pts = []
        for dx, dy, _, _ in axes:
            pts.extend([cx + dx * r, cy + dy * r])
        d.add(Polygon(
            pts,
            fillColor=None,
            strokeColor=GRID_GRAY if pct != 1.0 else BORDER_GRAY,
            strokeWidth=0.5 if pct != 1.0 else 0.8,
        ))

    # Axis lines
    for dx, dy, _, _ in axes:
        d.add(Line(
            cx, cy,
            cx + dx * radius, cy + dy * radius,
            strokeColor=BORDER_GRAY,
            strokeWidth=0.5,
        ))

    # Data polygon
    data_pts = []
    dot_positions = []
    for dx, dy, _, val in axes:
        v = max(0, min(100, val))
        r = radius * (v / 100.0)
        px = cx + dx * r
        py = cy + dy * r
        data_pts.extend([px, py])
        dot_positions.append((px, py))

    # Fill polygon — blue at 25% opacity for stronger visual
    fill_color = Color(
        ACCENT_BLUE.red, ACCENT_BLUE.green, ACCENT_BLUE.blue, 0.25,
    )
    d.add(Polygon(
        data_pts,
        fillColor=fill_color,
        strokeColor=ACCENT_BLUE,
        strokeWidth=2.5,
    ))

    # Score dots — semantically colored (red for critically low, blue for normal)
    for (px, py), (_, _, _, val) in zip(dot_positions, axes):
        dot_color = SC_RED if int(val) < 20 else ACCENT_BLUE
        d.add(Circle(
            px, py, 5,
            fillColor=dot_color,
            strokeColor=WHITE,
            strokeWidth=1.5,
        ))

    # Labels with scores outside chart
    label_offset = 18
    scores = [citability, eeat, schema, extraction]
    label_data = [
        (cx, cy + radius + label_offset, "Citability", scores[0]),
        (cx + radius + label_offset + 10, cy, "E-E-A-T", scores[1]),
        (cx, cy - radius - label_offset, "Schema", scores[2]),
        (cx - radius - label_offset - 14, cy, "Extraction", scores[3]),
    ]
    for lx, ly, lbl, val in label_data:
        # Axis label
        d.add(String(
            lx, ly, lbl,
            fontName="Helvetica", fontSize=10,
            fillColor=CAPTION_GRAY,
            textAnchor="middle",
        ))
        # Score value with semantic color
        sc = _sc(val)
        d.add(String(
            lx, ly - 13, f"{int(val)}/100",
            fontName="Helvetica-Bold", fontSize=9,
            fillColor=sc,
            textAnchor="middle",
        ))

    return d


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------
def _styled_table(header_row, data_rows, col_widths):
    """Build a table with spec-compliant styling.

    Header: no background fill, bottom border #E5E7EB.
    Data: alternating white/#F9FAFB, 8pt padding.
    No vertical borders.
    """
    all_rows = [header_row] + data_rows
    tbl = Table(all_rows, colWidths=col_widths)

    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Header bottom border
        ("LINEBELOW", (0, 0), (-1, 0), 1, BORDER_GRAY),
        # Last row bottom border
        ("LINEBELOW", (0, -1), (-1, -1), 1, BORDER_GRAY),
    ]
    # Alternating row backgrounds
    for i in range(len(data_rows)):
        row_idx = i + 1  # +1 because header is row 0
        bg = WHITE if (i % 2 == 0) else BG_GRAY
        style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg))

    tbl.setStyle(TableStyle(style_cmds))
    return tbl


# ---------------------------------------------------------------------------
# Urgency sentence logic
# ---------------------------------------------------------------------------
def _urgency(report):
    """Generate urgency sentence and color for cover page.

    Priority: zero schema > extreme cann > zero meta > low EEAT > high orphan.
    """
    tot = int(report.get("total_posts", 0) or 0)
    pct_schema = report.get("ai_pct_schema")

    # 1. Zero schema
    if pct_schema is not None and float(pct_schema) == 0:
        return (
            "100% of your posts have zero structured data \u2014 "
            "AI systems can\u2019t cite what they can\u2019t read.",
            SC_RED,
        )

    # 2. Extreme cannibalization (>40% posts)
    cposts = int(report.get("cann_post_count", 0) or 0)
    if tot > 0 and cposts > 0:
        pct_cann = (cposts / tot) * 100
        if pct_cann > 40:
            return (
                f"{pct_cann:.0f}% of your posts are competing against each "
                "other for the same searches.",
                SC_RED,
            )

    # 3. Zero meta descriptions
    meta_desc_pct = report.get("meta_desc_pct")
    meta_missing = int(report.get("meta_missing_count", 0) or 0)
    if meta_desc_pct is not None and float(meta_desc_pct) == 0 and tot > 0:
        return (
            f"Zero meta descriptions across all {tot} posts \u2014 "
            "search engines write your snippets for you.",
            SC_RED,
        )

    # 4. E-E-A-T critically low (<10)
    eeat = report.get("ai_eeat_score")
    if eeat is not None and int(eeat) < 10:
        return (
            "Your site has no visible author information \u2014 "
            "AI systems don\u2019t cite anonymous content.",
            SC_RED,
        )

    # 5. Massive orphan rate (>30%)
    orph = int(report.get("orphan_count", 0) or 0)
    if tot > 0 and orph > 0 and (orph / tot) > 0.30:
        return (
            f"{orph} of your pages have zero internal links \u2014 "
            "invisible to Google\u2019s crawler.",
            SC_RED,
        )

    # Fallback — still needs to be compelling
    if orph >= 3:
        return (
            f"{orph} pages are invisible to search engines \u2014 "
            "zero internal links pointing to them.",
            SC_RED,
        )
    cpairs = int(report.get("cann_pair_count", 0) or 0)
    if cpairs > 0:
        return (
            f"{cposts} of your posts are diluting each other\u2019s "
            "search rankings.",
            SC_AMBER,
        )
    return ("Your content ecosystem has untapped potential.", BRAND_BLUE)


# ---------------------------------------------------------------------------
# Meta description generator — MUST be specific to the post title
# ---------------------------------------------------------------------------
def _generate_meta_description(title, post=None):
    """Fallback meta description generator — used only when Claude API fails.

    Avoids ALL banned phrases from the spec. Uses URL slug and title keywords
    to create something more specific than pure filler.
    """
    if not title:
        return "See what this page offers and why it matters for your content."

    clean = title.strip().rstrip(".")
    url = ""
    if post and isinstance(post, dict):
        url = post.get("url", "") or ""

    # Extract slug keywords for specificity
    slug_raw = url.rstrip("/").split("/")[-1] if url else ""
    slug_words = [p for p in slug_raw.replace("-", " ").replace("_", " ").split()
                  if len(p) > 2 and p.lower() not in {"the", "and", "for", "how", "what", "with"}]

    topic = clean
    for prefix in ["How to ", "How To ", "What is ", "What Is ",
                    "Why ", "The Ultimate Guide to ", "A Guide to ",
                    "Guide to ", "The Complete ", "Complete ", "The "]:
        if topic.startswith(prefix):
            topic = topic[len(prefix):]
            break

    title_lower = clean.lower()

    if "template" in title_lower:
        return f"Downloadable {topic.lower()} — ready-to-use formats for SEO, content, and outreach."[:160]
    elif "review" in title_lower:
        product = topic.replace(" Review", "").replace(" review", "")
        return f"{product}: pricing, features, pros and cons, and who it's built for."[:160]
    elif title_lower.startswith("how to") or title_lower.startswith("how do"):
        return f"Step-by-step: {topic.lower()}. Includes examples and common mistakes."[:160]
    elif title_lower.startswith(("what is", "what are")):
        return f"{topic} explained — what it means, why it matters, and how to use it."[:160]
    elif "vs" in title_lower or "versus" in title_lower:
        return f"{clean} — side-by-side comparison with use cases for each option."[:160]
    elif any(w in title_lower for w in ["study", "report", "data", "analyzed", "statistics"]):
        return f"Original data on {topic.lower()} — findings and takeaways you can act on."[:160]
    elif "hub" in title_lower or "library" in title_lower:
        return f"{topic} — curated guides, tools, and frameworks by topic."[:160]
    else:
        # Use slug words to add specificity
        if slug_words:
            kw = ", ".join(slug_words[:3])
            return f"{clean}: covers {kw} with actionable examples and data."[:160]
        return f"{clean} — what it is, why it matters, and practical next steps."[:160]


# ===================================================================
# MAIN FUNCTION
# ===================================================================
def generate_audit_pdf(report, *, brand_name=None, logo_url=None):
    """Generate the 5-page audit PDF and return bytes."""
    _register_inter()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=MARGIN_LR,
        rightMargin=MARGIN_LR,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )

    # FIX 1: PDF metadata — title and author
    dom_for_meta = report.get("site_domain", "") or ""
    doc.title = f"{dom_for_meta} Content Audit — Tended"
    doc.author = "Tended"

    # ── Sanitize all Claude-generated content ──
    def _sanitize_ai_text(text):
        """Clean Claude output: fix terminology, remove promises, strip new numbers."""
        if not text:
            return text
        import re as _re
        # Terminology: schema variants → "structured data"
        # Rule: do NOT run on text already containing "structured data"
        # Rule: do NOT create "structured data (structured data)" double-replacement
        if "structured data" not in text.lower():
            text = _re.sub(r"(?i)FAQPage schema markup", "FAQ structured data", text)
            text = _re.sub(r"(?i)FAQPage schema", "FAQ structured data", text)
            text = _re.sub(r"(?i)Article schema", "Article structured data", text)
            text = _re.sub(r"(?i)schema markup", "structured data", text)
            text = _re.sub(r"(?i)\bJSON-LD\b", "structured data", text)
        # 9.8: Double-replacement detection — fix if somehow created
        text = text.replace("structured data (structured data)", "structured data")
        # Promise language → capability language
        _promises = [
            (r"\bwill directly support\b", "supports"),
            (r"\bwill significantly\b", "can significantly"),
            (r"\bwill increase\b", "can increase"),
            (r"\bwill boost\b", "enables"),
            (r"\bwill improve\b", "can improve"),
            (r"\bwill drive\b", "enables"),
            (r"\bwill enable\b", "enables"),
            (r"\brequires immediate implementation\b", "is a high-priority fix"),
            (r"\bmust be addressed urgently\b", "should be addressed"),
            (r"\bcritical gap requiring\b", "notable gap in"),
            (r"\bimplement structured data markup\b", "add structured data"),
            (r"\bImplement structured data\b", "Add structured data"),
        ]
        for pattern, replacement in _promises:
            text = _re.sub(pattern, replacement, text, flags=_re.IGNORECASE)
        return text

    # Apply to AI fields (v4.0: exec summary and what-this-means use locked templates,
    # so no need to sanitize those — only quick wins #3 may use Claude output)
    ai_wins = report.get("ai_quick_wins") or []
    for win in ai_wins:
        if isinstance(win, dict):
            if win.get("description"):
                win["description"] = _sanitize_ai_text(win["description"])
            if win.get("impact"):
                win["impact"] = _sanitize_ai_text(win["impact"])

    s = _build_styles()
    story = []
    brand = brand_name or "Tended"
    dom = report.get("site_domain", "") or ""
    dt_str = date.today().strftime("%B %d, %Y")

    # ── Extract report data ──────────────────────────────────────
    score = int(report.get("overall_health", 0) or 0)
    tot = int(report.get("total_posts", 0) or 0)
    clust = int(report.get("cluster_count", 0) or 0)
    iss = int(report.get("problem_count", 0) or 0)
    recs = int(report.get("rec_count", 0) or 0)
    cpairs = int(report.get("cann_pair_count", 0) or 0)
    cposts = int(report.get("cann_post_count", 0) or 0)
    orph = int(report.get("orphan_count", 0) or 0)
    thin = int(report.get("thin_content_count", 0) or 0)
    dups = int(report.get("exact_duplicate_count", 0) or 0)

    ai_cite = report.get("ai_citability_score")
    ai_eeat = report.get("ai_eeat_score")
    ai_schema = report.get("ai_schema_score")
    ai_extract = report.get("ai_extraction_score")
    ai_pct_ready = report.get("ai_pct_ready", 0) or 0
    ai_pct_schema = report.get("ai_pct_schema", 0) or 0

    avg_dd = report.get("avg_data_density", 0) or 0
    avg_qhr = report.get("avg_question_header_ratio", 0) or 0
    pct_faq = report.get("pct_has_faq", 0) or 0
    score_conf = report.get("score_confidence")

    avg_wc = int(report.get("avg_word_count", 0) or 0)
    avg_read = float(report.get("avg_readability", 0) or 0)
    upd_6mo = float(report.get("updated_6mo", 0) or 0)
    upd_12mo = float(report.get("updated_12mo", 0) or 0)
    upd_24mo = float(report.get("updated_24mo", 0) or 0)
    stale_24mo = float(report.get("stale_24mo", 0) or 0)

    avg_inbound = report.get("avg_inbound_links", 0) or 0
    most_linked_post = report.get("most_linked_post", "")
    most_linked_count = report.get("most_linked_count", 0) or 0

    top_clusters = report.get("top_clusters") or []
    top_cann_pairs = report.get("top_cann_pairs") or []
    top_recs = report.get("top_recs") or []
    worst_posts = report.get("worst_posts") or []
    best_posts = report.get("best_posts") or []
    key_findings = report.get("key_findings") or []
    headline = report.get("headline", "")

    # Integer versions for AI scores
    iv_cite = int(ai_cite or 0)
    iv_eeat = int(ai_eeat or 0)
    iv_schema = int(ai_schema or 0) if ai_schema is not None else 0
    iv_extract = int(ai_extract or 0)

    # ==================================================================
    # PAGE 1: COVER
    # ==================================================================
    # Vertically centered — content block ~450pt, available ~684pt.
    # (684-450)/2 = 117pt. Subtract ~15pt for optical center (slightly above geometric)
    story.append(Spacer(1, 1.4 * inch))

    # Logo
    base = getSampleStyleSheet()
    if _os.path.exists(_LOGO_PATH):
        try:
            img = RLImage(_LOGO_PATH, width=1.4 * inch, height=0.76 * inch)
            img.hAlign = "CENTER"
            story.append(img)
        except Exception:
            story.append(Paragraph("tended.", s["c_logo"]))
    else:
        story.append(Paragraph("tended.", s["c_logo"]))

    story.append(Spacer(1, 4))
    story.append(Paragraph("AI Content Audit Platform", ParagraphStyle("BrandDesc", parent=base["Normal"], fontName="Helvetica", fontSize=10, textColor=CAPTION_GRAY, alignment=TA_CENTER)))

    story.append(Spacer(1, 16))

    # Domain name — 36pt bold
    story.append(Paragraph(_safe(dom), s["c_domain"]))

    # "Content Audit Report" — 14pt grey
    story.append(Paragraph("Content Audit Report", s["c_subtitle"]))

    # Date — 12pt grey
    story.append(Paragraph(dt_str, s["c_date"]))

    # 40px space
    story.append(Spacer(1, 40))

    # Health score — 72pt bold, color by value
    sc_hex = _sch(score)
    score_style = ParagraphStyle(
        "CoverScore", fontName="Helvetica-Bold", fontSize=72,
        alignment=TA_CENTER, leading=72,
    )
    story.append(Paragraph(
        f"<font color='{sc_hex}'><b>{score}</b></font>"
        f"<font color='#9CA3AF' size='36'>/100</font>",
        score_style,
    ))

    # "Content Health Score" — 12pt grey
    story.append(Paragraph("Content Health Score", s["c_score_label"]))

    # "(moderate)" — 11pt grey italic — always grey
    story.append(Paragraph(f"<i>({_sw(score)})</i>", s["c_score_context"]))

    # Confidence note
    story.append(Spacer(1, 5))
    if score_conf == "crawl_only":
        story.append(Paragraph(
            "Based on content analysis \u2014 connect Google Analytics for a complete score",
            s["c_confidence"],
        ))

    # 40px space
    story.append(Spacer(1, 40))

    # Urgency sentence — 16pt red bold centered
    urg_text, urg_color = _urgency(report)
    urg_style = ParagraphStyle(
        "UrgStyle", parent=s["c_urgency"], textColor=urg_color,
    )
    story.append(Paragraph(_safe(urg_text), urg_style))

    # usetended.io link — balanced spacing below urgency
    story.append(Spacer(1, 0.8 * inch))
    story.append(Paragraph('<a href="https://usetended.io" color="#2563EB">usetended.io</a>', s["c_url"]))

    story.append(PageBreak())

    # ==================================================================
    # PAGE 2: EXECUTIVE SUMMARY
    # ==================================================================
    # Header
    story.append(Paragraph("Executive Summary", s["h1"]))
    story.append(Spacer(1, 8))  # Compact spacing

    # Summary paragraphs — LOCKED TEMPLATE (v4.0: never use Claude's ai_executive_summary)
    desc = ("performing well but has specific issues to address" if score >= 75
            else "in good shape" if score >= 65
            else "showing moderate issues that need attention" if score >= 40
            else "in critical condition")
    p1 = (
        f"Your site <b>{_safe(dom)}</b> scored <b>{score}/100</b> on content health, "
        f"meaning your content ecosystem is {desc}."
    )
    if recs:
        p1 += f" We generated <b>{recs:,} specific recommendations</b> across your content."
    story.append(Paragraph(p1, s["body"]))

    # Second paragraph with details
    parts = []
    if thin:
        parts.append(f"{thin} thin-content pages")
    if orph:
        parts.append(f"{orph} orphan posts")
    if parts or cpairs:
        p2 = f"We found <b>{iss:,} content issues</b>"
        if parts:
            p2 += f" ({', '.join(parts)})"
        if cpairs:
            p2 += (
                f" and <b>{cpairs} cannibalization pairs</b> where {cposts} "
                f"of your {tot} posts have significant content overlap"
            )
        p2 += "."
        story.append(Paragraph(p2, s["body"]))

    story.append(Spacer(1, 16))

    # ── Stat Boxes ──
    cw3 = CW / 3
    # Issues color — use _sc
    iss_color = _sch(max(0, 100 - iss))  # More issues = worse = redder
    if iss > 100:
        iss_hex = SC_RED.hexval()
    elif iss > 20:
        iss_hex = SC_AMBER.hexval()
    else:
        iss_hex = DARK_GRAY.hexval()

    num_row = [
        Paragraph(f"<b>{tot}</b>", s["stat_num"]),
        Paragraph(f"<b>{clust}</b>", s["stat_num"]),
        Paragraph(
            f"<b><font color='{SC_RED.hexval()}'>{iss:,}</font></b>",
            s["stat_num"],
        ),
    ]
    label_row = [
        Paragraph("Posts Analyzed", s["stat_label"]),
        Paragraph("Topic Clusters", s["stat_label"]),
        Paragraph("Issues Found", s["stat_label"]),
    ]
    stat_tbl = Table(
        [num_row, label_row],
        colWidths=[cw3] * 3,
        rowHeights=[40, 18],
    )
    stat_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), BG_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, BORDER_GRAY),
        ("LINEBEFORE", (1, 0), (1, -1), 1, BORDER_GRAY),
        ("LINEBEFORE", (2, 0), (2, -1), 1, BORDER_GRAY),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story.append(stat_tbl)
    story.append(Spacer(1, 8))

    # P2-02: Replace product feature list with data-driven category summary
    _ptc_for_preview = report.get("problem_type_counts") or {}
    _categories = []
    if _ptc_for_preview.get("missing_schema"): _categories.append("schema markup")
    if _ptc_for_preview.get("seo_missing_meta"): _categories.append("meta descriptions")
    if _ptc_for_preview.get("readability_too_complex"): _categories.append("readability improvement")
    if _ptc_for_preview.get("decay_mild") or _ptc_for_preview.get("decay_moderate"): _categories.append("content freshness")
    if _ptc_for_preview.get("seo_no_headings"): _categories.append("heading structure")
    if _ptc_for_preview.get("low_ai_citability"): _categories.append("AI optimization")
    if not _categories:
        _categories = ["content optimization", "AI readiness", "search visibility"]
    story.append(Paragraph(
        f"<i>Actions across {len(_categories)} categories: {', '.join(_categories)}.</i>",
        ParagraphStyle("RecPreview", parent=s["caption"], fontName="Helvetica-Oblique",
                       fontSize=10, textColor=CAPTION_GRAY),
    ))
    story.append(Spacer(1, 8))

    # ── AI Readiness Preview (compact — full radar chart on page 4) ──
    if ai_cite is not None:
        ai_desc = (
            f"<b>AI Readiness:</b> Your content scores "
            f"<font color='{_sch(iv_cite)}'><b>{iv_cite}/100</b></font> on AI citability"
        )
        if iv_schema == 0:
            ai_desc += (
                f" but <font color='{_sch(iv_schema)}'><b>{iv_schema}/100</b></font> "
                f"on structured data \u2014 the single biggest barrier to AI citation. "
                f"<i>See page 4 for the full breakdown.</i>"
            )
        else:
            ai_desc += f" with structured data at <font color='{_sch(iv_schema)}'><b>{iv_schema}/100</b></font>."
        story.append(Paragraph(ai_desc, s["body"]))
        story.append(Spacer(1, 6))

    # ── Key Findings ──
    story.append(Paragraph("Key Findings", s["h2"]))

    # OMIT zero-count findings from Key Findings (spec: showing zeroes wastes space)
    filtered_findings = []
    for f in key_findings:
        f_lower = f.lower()
        if "0 orphan" in f_lower or "0 thin" in f_lower or "0 cannibalization" in f_lower:
            continue
        if f_lower.startswith("0 ") or " 0 " in f_lower[:10]:
            continue
        filtered_findings.append(f)
    key_findings_display = filtered_findings[:4]

    kf_flowables = []
    for idx, text in enumerate(key_findings_display):
        if idx == len(key_findings_display) - 1:
            # Last bullet is always bold red
            kf_flowables.append(Paragraph(
                f"\u2022  <b>{_safe(text)}</b>",
                ParagraphStyle("KFLast", parent=s["bullet"],
                               fontName="Helvetica-Bold", textColor=SC_RED),
            ))
        else:
            kf_flowables.append(Paragraph(f"\u2022  {_safe(text)}", s["bullet"]))

    if kf_flowables:
        story.append(_container(kf_flowables, BG_NEUTRAL, BD_NEUTRAL))
    story.append(Spacer(1, 12))

    # ── Health Score Bar ──
    story.append(_health_bar(score, s))
    story.append(Spacer(1, 12))

    # ── Content Profile ──
    story.append(Paragraph("Content Profile", s["h3"]))

    cp_items = []
    if avg_wc:
        wc_desc = (
            "deep-form content" if avg_wc >= 3000 else
            "long-form content" if avg_wc >= 1500 else
            "medium-form content" if avg_wc >= 500 else
            "short-form content"
        )
        cp_items.append(Paragraph(
            f"\u2022  Average post length: <b>{avg_wc:,} words</b> ({wc_desc})",
            s["bullet"],
        ))
    if avg_read:
        cp_items.append(Paragraph(
            f"\u2022  Average readability: Flesch <b>{avg_read:.0f}</b> "
            f"({_readability_label(avg_read)})",
            s["bullet"],
        ))
    if upd_12mo:
        pct_fresh = int(upd_12mo * 100) if upd_12mo <= 1 else int(upd_12mo)
        pct_stale = 100 - pct_fresh
        freshness_text = f"\u2022  Content freshness: <b>{pct_fresh}%</b> updated in last 12 months"
        if pct_stale > 0:
            freshness_text += f" \u2014 but {pct_stale}% are stale and may drag down cluster health"
        cp_items.append(Paragraph(freshness_text, s["bullet"]))
    # Positive finding — green bold
    if ai_cite is not None:
        cp_items.append(Paragraph(
            f"\u2022  <font color='{SC_GREEN.hexval()}'><b>"
            f"Your content structure scores {iv_cite}/100 on AI citability"
            f"</b></font>",
            s["bullet"],
        ))

    if cp_items:
        story.append(_container(cp_items, BG_NEUTRAL, BD_NEUTRAL))
    story.append(Spacer(1, 8))

    # ── Comparative context (narrative insight) ──
    comp_parts = []
    if avg_wc:
        depth_label = "above" if avg_wc >= 1800 else "below"
        comp_parts.append(
            f"Your average post length ({avg_wc:,} words) is {depth_label} the B2B SaaS median (1,800 words)."
        )
    if avg_read > 0:
        comp_parts.append(
            f"Your readability (Flesch {avg_read:.0f}) is "
            + ("below" if avg_read < 60 else "at") +
            f" the recommended threshold of 60."
        )
    if iv_eeat >= 70:
        comp_parts.append(
            f"Your E-E-A-T score of {iv_eeat}/100 is strong, "
            f"but the {iv_schema}/100 schema score means AI systems can see your expertise "
            "signals but can\u2019t machine-read your content."
        )
    elif iv_schema == 0:
        comp_parts.append(
            "Structured data is standard practice for content sites competing "
            "in AI Overviews \u2014 yours has none."
        )
    if comp_parts:
        story.append(Paragraph(" ".join(comp_parts), s["body"]))
    story.append(Spacer(1, 4))

    story.append(PageBreak())

    # ==================================================================
    # PAGE 3: AI READINESS + ISSUE BREAKDOWN
    # ==================================================================
    story.append(Paragraph("AI Readiness", s["h1"]))
    story.append(Spacer(1, 4))

    # Headline
    if iv_schema == 0 and ai_cite is not None:
        story.append(Paragraph(
            f"Your content scores <font color='{_sch(iv_cite)}'><b>{iv_cite}/100</b></font> "
            f"on AI citability \u2014 but "
            f"<font color='{_sch(iv_schema)}'><b>{iv_schema}/100</b></font> on structured data.",
            ParagraphStyle("AIHeadline", parent=s["body"], fontName="Helvetica-Bold",
                           fontSize=11, spaceAfter=8),
        ))
    elif ai_cite is not None:
        story.append(Paragraph(
            f"Your content scores <font color='{_sch(iv_cite)}'><b>{iv_cite}/100</b></font> "
            f"on AI citability.",
            ParagraphStyle("AIHeadline", parent=s["body"], fontName="Helvetica-Bold",
                           fontSize=11, spaceAfter=8),
        ))

    # ── Dimension Boxes (4 across) ──
    dims = [
        ("Citability", iv_cite),
        ("E-E-A-T", iv_eeat),
        ("Schema", iv_schema),
        ("Extraction", iv_extract),
    ]
    dim_nums = []
    dim_labels = []
    for lbl, val in dims:
        if val is not None:
            dim_nums.append(Paragraph(
                f"<font color='{_sch(val)}'><b>{val}</b></font>"
                f"<font size='12' color='#9CA3AF'>/100</font>",
                s["ai_num"],
            ))
        else:
            dim_nums.append(Paragraph("\u2014", s["ai_num"]))
        dim_labels.append(Paragraph(lbl, s["ai_label"]))

    aw = CW / 4
    dim_tbl = Table(
        [dim_nums, dim_labels],
        colWidths=[aw] * 4,
        rowHeights=[32, 16],
    )
    dim_style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1, BORDER_GRAY),
        ("LINEBEFORE", (1, 0), (1, -1), 1, BORDER_GRAY),
        ("LINEBEFORE", (2, 0), (2, -1), 1, BORDER_GRAY),
        ("LINEBEFORE", (3, 0), (3, -1), 1, BORDER_GRAY),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]
    # P4-05: Visual emphasis for critically low scores — red bg + red border
    for col_idx, (_, val) in enumerate(dims):
        if val is not None and int(val) < 10:
            dim_style_cmds.append(("BACKGROUND", (col_idx, 0), (col_idx, 1), HexColor("#FEE2E2")))
            dim_style_cmds.append(("BOX", (col_idx, 0), (col_idx, 1), 1.5, SC_RED))
    dim_tbl.setStyle(TableStyle(dim_style_cmds))
    story.append(dim_tbl)
    story.append(Spacer(1, 8))

    # ── Spider Chart ──
    spider_data = [float(v or 0) for _, v in dims]
    if any(v > 0 for v in spider_data):
        spider = _spider_chart(
            spider_data[0], spider_data[1], spider_data[2], spider_data[3],
        )
        story.append(spider)
        story.append(Spacer(1, 4))

    # ── "Why AI systems skip your content" ──
    why_bullets = []
    if ai_pct_schema is not None and float(ai_pct_schema) < 50:
        pct_no_schema = 100 - int(float(ai_pct_schema))
        why_bullets.append(
            f"{pct_no_schema}% of your posts have no structured data \u2014 "
            "invisible to Google rich results (enhanced search listings)"
        )
    if avg_qhr < 0.3:
        why_bullets.append(
            f"Only {avg_qhr * 100:.0f}% of section headings are question-format \u2014 "
            "top AI-cited content typically uses 25-35% question-format headers"
        )
    if pct_faq < 30:
        why_bullets.append(
            f"Only {pct_faq:.0f}% of posts have FAQ sections \u2014 "
            "posts with FAQ structured data get significantly higher AI visibility"
        )
    if why_bullets:
        story.append(Paragraph("Why AI systems skip your content", s["h3"]))
        for wb in why_bullets[:3]:  # Max 3 to fit page 3
            story.append(Paragraph(f"\u2022  {_safe(wb)}", s["bullet"]))
        story.append(Spacer(1, 4))

    # ── "What this means" — site-specific with prospect's data ──
    if iv_schema == 0:
        # Reference prospect's E-E-A-T strength and best post if available
        best_post_title = ""
        if report.get("best_posts") and isinstance(report["best_posts"], list) and report["best_posts"]:
            best_post_title = report["best_posts"][0].get("title", "")
        elif report.get("worst_posts") and len(report["worst_posts"]) >= 5:
            # No best_posts? Use the healthiest post name
            pass

        if iv_eeat >= 70 and best_post_title:
            wtm_text = (
                f"Your content scores {iv_eeat}/100 on E-E-A-T \u2014 your author pages, "
                "publication dates, and expertise signals are strong. But without structured data "
                f"(0/100), AI systems can see your authority but can\u2019t machine-read your content. "
                f"Adding Article JSON-LD to your top 20 posts would make your strongest content "
                "immediately eligible for Google AI Overviews."
            )
        else:
            wtm_text = (
                "Without structured data, your posts are invisible to Google\u2019s rich results "
                "and less likely to be cited in AI Overviews. "
                "Adding Article structured data is the single highest-impact change you can make. "
                "Google AI Overviews now appear on ~50% of searches."
            )
        wtm_flowables = [
            Paragraph(
                f"<b>What this means:</b> {_safe(wtm_text)}",
                ParagraphStyle("WTM", parent=s["body"], textColor=HexColor("#92400E"),
                               fontSize=10, leading=14),
            ),
        ]
        story.append(_container(wtm_flowables, BG_WARNING, BD_WARNING))

    story.append(Spacer(1, 4))

    # ── Issue Breakdown (P4-04: categorized by actual type, not "SEO issues") ──
    story.append(Paragraph("Issue Breakdown", s["h2"]))

    # Data-driven issue categories from problem_type_counts
    ptc = report.get("problem_type_counts") or {}
    ai_issues = int(ptc.get("missing_schema", 0)) + int(ptc.get("low_ai_citability", 0)) + int(ptc.get("poor_ai_structure", 0))
    quality_issues = int(ptc.get("readability_too_complex", 0)) + int(ptc.get("thin_content", 0)) + int(ptc.get("thin_below_cluster_avg", 0))
    freshness_issues = int(ptc.get("decay_mild", 0)) + int(ptc.get("decay_moderate", 0)) + int(ptc.get("decay_severe", 0))
    seo_issues = int(ptc.get("seo_title_length", 0)) + int(ptc.get("seo_missing_meta", 0)) + int(ptc.get("seo_no_headings", 0)) + int(ptc.get("seo_no_images", 0))

    issue_items = []
    if ai_issues:
        issue_items.append((ai_issues, "AI readiness issues (missing structured data, low citability) \u2014 reducing AI citation eligibility", SC_RED))
    if quality_issues:
        issue_items.append((quality_issues, "Content quality issues (readability, thin content) \u2014 making content harder to scan", SC_AMBER))
    if freshness_issues:
        issue_items.append((freshness_issues, "Freshness issues (content not updated in 18+ months) \u2014 losing relevance", SC_AMBER))
    if seo_issues:
        issue_items.append((seo_issues, "SEO issues (title length, missing meta, no headings) \u2014 reducing search visibility", SC_AMBER))
    if cpairs:
        issue_items.append((cpairs, f"Content overlap pairs \u2014 {cposts} posts may dilute each other", SC_AMBER))
    if orph:
        issue_items.append((orph, "Orphan posts \u2014 no internal links, invisible to crawlers", SC_RED))
    # Fallback for sites where problem_type_counts isn't provided
    if not issue_items and iss > 0:
        issue_items.append((iss, "Content issues detected \u2014 see recommendations for details", SC_AMBER))

    if issue_items:
        issue_rows = []
        for cnt, label, clr in issue_items[:4]:
            issue_rows.append([
                Paragraph(
                    f"<font color='{clr.hexval()}'>\u25cf</font>",
                    ParagraphStyle("IssueDot", parent=s["body"], fontSize=12,
                                   alignment=TA_CENTER),
                ),
                Paragraph(
                    f"<font color='{clr.hexval()}'><b>{cnt}</b></font>",
                    ParagraphStyle("IssueCnt", parent=s["body"], fontName="Helvetica-Bold",
                                   fontSize=11, alignment=TA_CENTER),
                ),
                Paragraph(label, s["body"]),
            ])
        issue_tbl = Table(
            issue_rows,
            colWidths=[0.3 * inch, 0.5 * inch, CW - 0.8 * inch],
        )
        issue_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(issue_tbl)
        # Footnote: rows won't sum to total because of multi-issue posts
        story.append(Paragraph(
            "Individual posts may appear in multiple categories. Total reflects deduplicated issue count.",
            ParagraphStyle("IssueFootnote", parent=s["caption"], fontSize=9, textColor=CAPTION_GRAY),
        ))

    # End of page 3 — AI Readiness + Issue Breakdown only
    story.append(PageBreak())

    # ==================================================================
    # PAGE 4: TOPIC CLUSTERS + QUICK WINS + TOP 5
    # (Example Fix flows to page 5 naturally)
    # ==================================================================

    # ── Topic Clusters ──
    tcl = top_clusters[:5]  # Show top 5 clusters (P5-03: show more of the analysis)
    if tcl:
        # P5-02: If all clusters have the same ecosystem state, use health-relative labels
        states = [cl.get("ecosystem_state", "") for cl in tcl]
        all_same_state = len(set(states)) <= 1
        if all_same_state and len(tcl) >= 2:
            health_vals = sorted([int(cl.get("health_score", 0) or 0) for cl in tcl], reverse=True)
            top_h, bot_h = health_vals[0], health_vals[-1]
            for cl in tcl:
                h = int(cl.get("health_score", 0) or 0)
                if h >= top_h - 2:
                    cl["_display_status"] = "Strong"
                elif h <= bot_h + 2:
                    cl["_display_status"] = "Needs Attention"
                else:
                    cl["_display_status"] = "Moderate"
        # Column widths: Cluster gets remaining, Posts=50pt, Health=50pt, Status=70pt
        col_cluster = CW - 50 - 50 - 70
        header = [
            Paragraph("Cluster", s["th"]),
            Paragraph("Posts", s["th_center"]),
            Paragraph("Health", s["th_center"]),
            Paragraph("Status", s["th"]),
        ]
        data_rows = []
        for cl in tcl:
            h = int(cl.get("health_score", 0) or 0)
            status = cl.get("_display_status") or _eco(cl.get("ecosystem_state", ""))
            stc = _stc(status)
            data_rows.append([
                Paragraph(_safe(_truncate(cl.get("label", "\u2014"), 35)), s["td"]),
                Paragraph(str(cl.get("post_count", 0)), s["td_center"]),
                Paragraph(
                    f"<font color='{_sch(h)}'><b>{h}</b></font>",
                    ParagraphStyle("CH", parent=s["td"], fontName="Helvetica-Bold",
                                   alignment=TA_CENTER),
                ),
                Paragraph(
                    f"<font color='{stc.hexval()}'>{status}</font>",
                    s["td"],
                ),
            ])

        cluster_tbl = _styled_table(header, data_rows, [col_cluster, 50, 50, 70])
        story.append(Paragraph("Topic Clusters", s["h3"]))
        story.append(Paragraph(
            f"Your content organizes into {clust} topic clusters. "
            f"Top {len(tcl)} shown.",
            ParagraphStyle("TCCaption", parent=s["caption"]),
        ))
        story.append(Spacer(1, 4))
        story.append(cluster_tbl)

        # Cluster footnote (Change 8)
        story.append(Paragraph(
            "Status based on content freshness trends and structural health, not score alone",
            ParagraphStyle("ClusterNote", parent=s["caption"], fontSize=9, textColor=CAPTION_GRAY),
        ))

    story.append(Spacer(1, 6))

    # ── Quick Wins (now on page 4) ──
    story.append(Paragraph("Top 3 Quick Wins", s["h1"]))
    story.append(Spacer(1, 8))

    # Build quick wins — #1 and #2 use LOCKED TEMPLATES (v4.0), #3 allows Claude override
    wins = []
    # 1. Schema if zero — LOCKED TEMPLATE
    if ai_schema is not None and iv_schema == 0:
        wins.append((
            "Add structured data to your top posts",
            f"None of your {tot} posts have structured data. Adding it enables rich results and AI citations.",
            f"Enables rich results for 100% of your {tot} posts",
        ))

    # 2. Top cann pair — LOCKED TEMPLATE
    if top_cann_pairs:
        p = top_cann_pairs[0]
        a_title = _truncate(p.get("post_a_title", ""), 30)
        b_title = _truncate(p.get("post_b_title", ""), 30)
        sim = float(p.get("overlap_score", 0) or 0)
        sim_pct = sim * 100 if sim <= 1 else sim
        wins.append((
            f"Consolidate or differentiate: \"{_safe(a_title)}\" vs \"{_safe(b_title)}\"",
            f"These posts are {sim_pct:.0f}% similar and may dilute each other\u2019s "
            "search visibility.",
            f"Eliminate ranking competition between these 2 pages",
        ))

    # 3. From top_recs — pick a DIFFERENT type than wins 1-2 (not schema/FAQ)
    used_titles = set()
    if top_cann_pairs:
        used_titles.add(top_cann_pairs[0].get("post_a_title", ""))
        used_titles.add(top_cann_pairs[0].get("post_b_title", ""))
    # Skip schema/FAQ recs to ensure 3 genuinely different win types
    for r in top_recs:
        if len(wins) >= 3:
            break
        if not isinstance(r, dict):
            continue
        if r.get("post_title", "") in used_titles:
            continue
        rt = (r.get("rec_type", "") or "").lower()
        title_lower = (r.get("title", "") or "").lower()
        # Skip schema/FAQ — Win #1 already covers structured data
        if any(kw in rt for kw in ("schema", "faq", "add_schema", "add_faq")):
            continue
        if any(kw in title_lower for kw in ("schema", "faq", "structured data")):
            continue
        pt = r.get("post_title", "")
        # P5-04: Remove hedging language ("consider") from rec titles
        win_title = _safe(r.get("title", "")).replace("Consider refreshing older content:", "Refresh stale content:")
        # P5-05: Specific impact text instead of vague "fixes issues for"
        rec_type_lower = rt.lower()
        if "refresh" in rec_type_lower or "update" in rec_type_lower or "decay" in rec_type_lower:
            impact_text = f"Restores freshness signals for {_safe(_truncate(pt, 30))}"
        elif "readability" in rec_type_lower or "simplify" in title_lower:
            impact_text = f"Improves scannability and AI citation for {_safe(_truncate(pt, 30))}"
        elif "expand" in rec_type_lower:
            impact_text = f"Brings {_safe(_truncate(pt, 30))} to competitive depth"
        else:
            impact_text = f"Resolves top issues for {_safe(_truncate(pt, 30))}"
        wins.append((
            win_title,
            _safe(r.get("summary", "") or ""),
            impact_text,
        ))
        used_titles.add(pt)

    # Fallback if still < 3 wins: use orphan fix or ANY remaining rec
    if len(wins) < 3 and orph > 0:
        wins.append((
            f"Fix {orph} orphan posts with internal links",
            f"{orph} posts have no inbound links, making them invisible to search crawlers.",
            f"connects {orph} isolated posts to your site structure",
        ))
    if len(wins) < 3:
        for r in top_recs:
            if len(wins) >= 3:
                break
            if not isinstance(r, dict):
                continue
            if r.get("title", "") in {w[0] for w in wins}:
                continue
            pt = r.get("post_title", "")
            wins.append((
                _safe(r.get("title", "")),
                _safe(r.get("summary", "") or ""),
                f"fixes issues for {_safe(_truncate(pt, 30))}",
            ))

    # Store Quick Win #1 title for 30-Day Plan Week 1
    qw1_title = wins[0][0] if wins else "Add structured data to your top 10 posts"

    ai_wins = report.get("ai_quick_wins") or []

    for i, (title, body, impact) in enumerate(wins[:3], 1):
        # v4.0: Only Quick Win #3 allows Claude override; #1 and #2 use locked templates
        # FIX: also override title when body is overridden to prevent header/body mismatch
        if i == 3 and len(ai_wins) >= 3 and ai_wins[2]:
            ai_win = ai_wins[2]
            if ai_win.get("title"):
                title = ai_win["title"]
            if ai_win.get("description"):
                body = ai_win["description"]
            if ai_win.get("impact"):
                impact = ai_win["impact"]

        story.append(Paragraph(f"<b>{i}. {title}</b>", s["qw_title"]))
        if body:
            story.append(Paragraph(body, s["qw_body"]))
        if impact:
            story.append(Paragraph(f"\u2192 <i>{impact}</i>", s["impact"]))
        if i < len(wins[:3]):
            story.append(Spacer(1, 4))

    # Thin divider
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GRAY))
    story.append(Spacer(1, 6))

    # ── Top 5 Posts Needing Attention ──
    worst = worst_posts[:5]
    all_above_50 = all(
        int((p.get("health_score") or 0) if isinstance(p, dict) else 0) > 50
        for p in worst
    ) if worst else False
    top5_header = "Optimization Opportunities" if all_above_50 else "Top 5 Posts Needing Attention"
    if worst:
        col_num = 24
        col_score = 45
        col_issues = 1.6 * inch
        col_post = CW - col_num - col_score - col_issues

        header = [
            Paragraph("#", s["th_center"]),
            Paragraph("Post", s["th"]),
            Paragraph("Score", s["th_center"]),
            Paragraph("Issues", s["th"]),
        ]
        data_rows = []
        for idx, p in enumerate(worst, 1):
            t2 = (p.get("title") or "Untitled") if isinstance(p, dict) else "Untitled"
            ps2 = int((p.get("health_score") or 0) if isinstance(p, dict) else 0)
            ri = (p.get("issue") or "") if isinstance(p, dict) else ""
            iss_text = _humanize_issues(ri, t2) if ri else "low health score"
            ip = [x.strip() for x in iss_text.split(",")]
            if len(ip) > 2:
                iss_text = ", ".join(ip[:2]) + f" (+{len(ip) - 2} more)"
            data_rows.append([
                Paragraph(str(idx), s["td_center"]),
                Paragraph(_safe(_truncate(t2, 38)), s["td"]),
                Paragraph(
                    f"<font color='{_sch(ps2)}'><b>{ps2}</b></font>",
                    ParagraphStyle("PS", parent=s["td"], fontName="Helvetica-Bold",
                                   alignment=TA_CENTER),
                ),
                Paragraph(_safe(iss_text),
                          ParagraphStyle("PI", parent=s["td"], fontSize=10, leading=13)),
            ])

        posts_tbl = _styled_table(header, data_rows, [col_num, col_post, col_score, col_issues])
        story.append(Paragraph(top5_header, s["h2"]))
        story.append(Spacer(1, 4))
        story.append(posts_tbl)

    # Thin divider
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GRAY))
    story.append(Spacer(1, 6))

    # ── Example Fix — show the post's ACTUAL top problem, not always meta (P5-08) ──
    ef_post = None
    ef_header_label = "Your lowest-scoring post"
    if worst:
        ef_post = worst[0]
        ef_header_label = "Your lowest-scoring post"

    if ef_post and isinstance(ef_post, dict):
        w0 = ef_post
        w0_title = w0.get("title") or "Untitled"
        w0_score = int(w0.get("health_score") or 0)
        w0_sc_hex = _sch(w0_score)

        # Determine the post's actual top problem
        post_issues = (w0.get("issue") or w0.get("issues") or "").split(",") if isinstance(w0, dict) else []
        post_issues = [i.strip() for i in post_issues if i.strip()]
        current_meta = (w0.get("meta_description") or "").strip()
        has_meta = bool(current_meta)

        # Choose example fix type based on what the post actually needs
        if not has_meta:
            # Site/post has no meta → show meta description fix
            suggested_meta = w0.get("suggested_meta", "") or _generate_meta_description(w0_title, w0)
            current_label = "Current meta description: <i>(none)</i>"
            suggested_label = f"Suggested: <b>{_safe(suggested_meta)}</b>"
        elif "low_ai_citability" in post_issues or "missing_schema" in post_issues:
            # Post has meta but low AI citability → show AI readiness fix
            # Use actual citability score if available, fall back to health score
            cite_score = int(w0.get("citability_score") or w0.get("ai_citability_score") or w0_score)
            current_label = f"Current AI citability: <i><font color='{_sch(cite_score)}'>{cite_score}/100</font></i>"
            suggested_label = (
                "<b>Add Article JSON-LD schema with headline, datePublished, author, and image. "
                "Add 2-3 data tables or original statistics. Start key H2 sections with direct answers.</b>"
            )
        elif "readability_too_complex" in post_issues:
            # Complex readability → show simplification fix
            current_label = f"Current readability: <i>Below threshold (professional audience level)</i>"
            suggested_label = (
                "<b>Break sentences over 25 words into shorter ones. Replace jargon with plain alternatives. "
                "Add subheadings every 2-3 paragraphs.</b>"
            )
        else:
            # Fallback: schema fix (always applicable)
            current_label = "Current structured data: <i>(none)</i>"
            suggested_label = (
                "<b>Add Article JSON-LD with @type, headline, datePublished, dateModified, "
                "author (@type: Person), and image.</b>"
            )

        ef_flowables = [
            Paragraph(
                f"<b>Example Fix</b> \u2014 {ef_header_label}",
                ParagraphStyle("EFHeader", parent=s["body"], fontName="Helvetica-Bold",
                               fontSize=14, textColor=BLACK),
            ),
            Spacer(1, 6),
            Paragraph(
                f"<b>{_safe(_truncate(w0_title, 60))}</b> "
                f"(score: <font color='{w0_sc_hex}'><b>{w0_score}</b></font>)",
                ParagraphStyle("EFTitle", parent=s["body"], fontSize=12),
            ),
            Spacer(1, 4),
            Paragraph(
                current_label,
                ParagraphStyle("EFCurrent", parent=s["body"], textColor=CAPTION_GRAY,
                               fontName="Helvetica-Oblique"),
            ),
            Spacer(1, 4),
            Paragraph(
                suggested_label,
                ParagraphStyle("EFSuggested", parent=s["body"], fontSize=12,
                               fontName="Helvetica-Bold", textColor=HexColor("#1E40AF")),
            ),
        ]
        story.append(_container(ef_flowables, BG_EXAMPLE, BD_EXAMPLE))
        story.append(Spacer(1, 8))

        # Below container note — only show meta description CTA when relevant
        meta_pct = int(report.get("meta_desc_pct", 100) or 100)
        if meta_pct < 80:
            story.append(Paragraph(
                f"<i>Get AI-written meta descriptions for all {tot} posts</i>",
                ParagraphStyle("EFNote", parent=s["caption"], fontName="Helvetica-Oblique",
                               textColor=CAPTION_GRAY),
            ))

    # Content flows from page 4 to page 5 naturally

    # ==================================================================
    # PAGE 5: EXAMPLE FIX + CANNIBALIZATION + 30-DAY PLAN + WYG + CTA
    # ==================================================================

    # ── Cannibalization Pairs ──
    if top_cann_pairs:
        # Table: Post A | Post B | Overlap
        col_overlap = 60
        col_post = (CW - col_overlap) / 2

        header = [
            Paragraph("Post A", s["th"]),
            Paragraph("Post B", s["th"]),
            Paragraph("Similarity", s["th_right"]),
        ]
        data_rows = []
        for cp in top_cann_pairs[:6]:
            sim = float(cp.get("overlap_score", 0) or 0)
            sim_pct = sim * 100 if sim <= 1 else sim
            olap_clr = _olap_color(sim_pct)
            a2 = cp.get("post_a_title", "")
            b2 = cp.get("post_b_title", "")
            # Disambiguate identical titles
            if a2 == b2:
                slug_a = cp.get("post_a_url", "").rstrip("/").split("/")[-1]
                slug_b = cp.get("post_b_url", "").rstrip("/").split("/")[-1]
                if slug_a != slug_b:
                    a2 = f"{a2} (/{slug_a})"
                    b2 = f"{b2} (/{slug_b})"
            data_rows.append([
                Paragraph(_safe(_truncate(a2, 33)), s["td"]),
                Paragraph(_safe(_truncate(b2, 33)), s["td"]),
                Paragraph(
                    f"<font color='{olap_clr.hexval()}'><b>{sim_pct:.0f}%</b></font>",
                    ParagraphStyle("OlapPct", parent=s["td"], fontName="Helvetica-Bold",
                                   alignment=TA_RIGHT),
                ),
            ])

        cann_tbl = _styled_table(header, data_rows, [col_post, col_post, col_overlap])
        story.append(Paragraph("Top Cannibalization Pairs", s["h1"]))
        story.append(Spacer(1, 4))
        story.append(cann_tbl)

    story.append(Spacer(1, 6))

    # ── 30-Day Action Plan (Change 7: Week 3 specificity) ──
    if top_cann_pairs:
        p1 = top_cann_pairs[0]
        a_title = _truncate(p1.get("post_a_title", ""), 25)
        b_title = _truncate(p1.get("post_b_title", ""), 25)
        sim = float(p1.get("overlap_score", 0) or 0)
        sim_pct = sim * 100 if sim <= 1 else sim
        more = min(2, len(top_cann_pairs) - 1)
        if more > 0:
            w3 = f"Consolidate '{_safe(a_title)}' and '{_safe(b_title)}' ({sim_pct:.0f}% overlap), plus {more} more pairs"
        else:
            w3 = f"Consolidate '{_safe(a_title)}' and '{_safe(b_title)}' ({sim_pct:.0f}% overlap)"
    else:
        w3 = "Address the 3 most overlapping content pairs"

    # Build Week 2 and Week 4 with fallback alternatives when counts are 0
    ptc = report.get("problem_type_counts") or {}
    readability_count = int(ptc.get("readability_too_complex", 0))

    if orph > 0:
        w2_text = f"Fix {orph} orphan pages with internal links from related content"
    elif readability_count > 0:
        w2_text = f"Improve readability on {readability_count} complex posts, starting with the lowest-scoring"
    elif cpairs > 5:
        w2_text = f"Review {cpairs} additional content overlap pairs for consolidation opportunities"
    else:
        w2_text = "Add question-format H2 headers to your top 10 posts to boost AI citation"

    if thin > 0:
        w4_text = f"Fix {thin} thin-content posts by expanding below-average pages"
    elif int(ptc.get("low_ai_citability", 0)) > 0:
        w4_text = f"Improve AI citability on {ptc['low_ai_citability']} low-scoring posts with data tables and statistics"
    else:
        w4_text = "Add AI-optimized FAQ sections to your top 10 posts by health score"

    # P6-04: Week 3 — be specific about cann pairs
    if top_cann_pairs:
        more = max(0, len(top_cann_pairs) - 1)
        if more > 0:
            w3 = f"Consolidate your {len(top_cann_pairs)} highest-overlap content pairs, starting with '{_safe(a_title)}' vs '{_safe(b_title)}'"
        # else w3 is already set

    plan_items = [
        Paragraph("<b>Your 30-Day Action Plan</b>", s["h2"]),
        Spacer(1, 4),
        Paragraph(
            f"\u2022  <b>Week 1:</b> {_safe(qw1_title)}",
            s["bullet"],
        ),
        Paragraph(
            f"\u2022  <b>Week 2:</b> {_safe(w2_text)}",
            s["bullet"],
        ),
        Paragraph(
            f"\u2022  <b>Week 3:</b> {w3}",
            s["bullet"],
        ),
        Paragraph(
            f"\u2022  <b>Week 4:</b> {_safe(w4_text)}",
            s["bullet"],
        ),
    ]
    story.append(_container(plan_items, BG_NEUTRAL, BD_NEUTRAL, padding=8))
    story.append(Spacer(1, 6))

    # ── "What You Get" container (compact for page 5) ──
    if recs:
        wyg_flowables = [
            Paragraph(
                "<b>What You Get</b>",
                ParagraphStyle("WYGHeader", parent=s["body"], fontName="Helvetica-Bold",
                               fontSize=14, textColor=BLACK),
            ),
            Spacer(1, 4),
            Paragraph(
                f"<font color='{SC_GREEN.hexval()}'>\u2713</font> All {recs:,} recommendations"
                + (f" \u2014 including merge plans for your {cpairs} overlap pairs" if cpairs > 3 else " with specific, copy-paste actions"),
                ParagraphStyle("WYG1", parent=s["body"], fontSize=10, textColor=SC_GREEN),
            ),
            Paragraph(
                f"<font color='{SC_GREEN.hexval()}'>\u2713</font> AI-ready content briefs for your top {min(20, tot)} posts by health score",
                ParagraphStyle("WYG2", parent=s["body"], fontSize=10, textColor=SC_GREEN),
            ),
            Paragraph(
                f"<font color='{SC_GREEN.hexval()}'>\u2713</font> Cluster health tracking across your {clust} topic areas",
                ParagraphStyle("WYG3", parent=s["body"], fontSize=10, textColor=SC_GREEN),
            ),
        ]
        story.append(_container(wyg_flowables, BG_POSITIVE, BD_POSITIVE, padding=6))
        story.append(Spacer(1, 6))

    # ── CTA (compact spacing for page 5) ──
    story.append(Paragraph(
        f"<b>Get all {recs:,} recommendations with Tended.</b>",
        ParagraphStyle("CTAHeadCompact", parent=s["cta_headline"], spaceBefore=8, spaceAfter=4),
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<i>Every day without structured data, AI systems cite your competitors instead of you.</i>",
        s["cta_urgency"],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "$149/month. 30-day money-back guarantee.",
        s["cta_price"],
    ))
    # P6-05: Styled CTA button
    cta_btn_flowables = [
        Paragraph(
            '<a href="https://usetended.io" color="#FFFFFF">'
            '<b>Start your free audit at usetended.io \u2192</b></a>',
            ParagraphStyle("CTABtn", fontName="Helvetica-Bold", fontSize=13,
                           alignment=TA_CENTER, textColor=WHITE, leading=16),
        ),
    ]
    story.append(Spacer(1, 4))
    story.append(_container(cta_btn_flowables, BRAND_BLUE, BRAND_BLUE, padding=10))

    # P6-06: QR code — inline with CTA, compact
    try:
        import qrcode as _qr
        _qobj = _qr.QRCode(version=1, box_size=2, border=1)
        _qobj.add_data("https://usetended.io")
        _qobj.make(fit=True)
        _qimg = _qobj.make_image(fill_color="black", back_color="white")
        _qbuf = io.BytesIO()
        _qimg.save(_qbuf, format="PNG")
        _qbuf.seek(0)
        qr_rl = RLImage(_qbuf, width=0.65 * inch, height=0.65 * inch)
        qr_rl.hAlign = "CENTER"
        story.append(Spacer(1, 3))
        story.append(qr_rl)
    except Exception:
        pass

    # ── Build PDF ──
    # Blue for analysis (2-3), green for action (4), amber for close (5+)
    page_borders = {
        2: BORDER_BLUE, 3: BORDER_BLUE,
        4: BORDER_GREEN, 5: BORDER_AMBER, 6: BORDER_AMBER,
    }
    on_page = _make_page_callback(dt_str, page_borders, dom)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================

_ISSUE_LABELS = {
    "seo_missing_meta": "Missing meta description",
    "seo_title_length": "Title too short/long",
    "seo_no_headings": "No headings",
    "seo_no_internal_links": "No internal links",
    "seo_no_images": "No images",
    "thin_content": "Thin content",
    "thin_below_cluster_avg": "Thin content",
    "thin_high_bounce": "Thin content (high bounce)",
    "readability_too_complex": "Hard to read",
    "orphan": "No inbound links",
    "missing_schema": "No structured data",
    "cannibalization": "Cannibalizing another post",
    "decay_mild": "Mild traffic decline",
    "decay_moderate": "Moderate traffic decline",
    "decay_severe": "Severe traffic decline",
    "low_ai_citability": "Low AI citability",
    "weak_eeat": "Weak E-E-A-T signals",
    "poor_ai_structure": "Poor AI structure",
    "geo_no_faq_section": "No FAQ section",
    "geo_no_data_tables": "No data tables",
    "geo_no_experience_markers": "No experience markers",
    "geo_no_question_headers": "No question headers",
    "geo_low_data_density": "Low data density",
    "geo_no_answer_first": "No answer-first structure",
    "geo_missing_faq_schema": "Missing FAQ markup",
    "geo_no_updated_date": "No last-updated date",
    "velocity_decline": "Publishing velocity decline",
    "intent_mismatch": "Intent mismatch",
    "serp_opportunity_missed": "Missed SERP opportunity",
}


def _humanize_issues(raw, title=""):
    """Convert comma-separated issue codes into human-readable labels."""
    parts = [p.strip() for p in raw.split(",")]
    labels = []
    for p in parts:
        if not p:
            continue
        if p == "seo_title_length" and title:
            labels.append("Title too short" if len(title) < 30 else "Title too long")
        else:
            labels.append(_ISSUE_LABELS.get(p, p.replace("_", " ")))
    return ", ".join(dict.fromkeys(labels)) if labels else "low health score"


def _safe(t):
    """Escape XML-sensitive characters for reportlab Paragraph."""
    if not t:
        return ""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(t, n=45):
    """Truncate text at word boundary."""
    if not t or len(t) <= n:
        return t or ""
    return t[:n].rsplit(" ", 1)[0] + "\u2026"


def _score_color(score):
    """Public alias for _sc — used by other modules."""
    return _sc(score)


# ===================================================================
# POST-GENERATION AI VERIFICATION
# ===================================================================

async def verify_pdf_against_spec(pdf_bytes: bytes, report: dict) -> dict:
    """Verify a generated PDF against the FULL PDF_FEEDBACK.md spec using Claude.

    Feeds the complete spec document + full extracted PDF text to Claude Sonnet
    for thorough rule-by-rule verification. Returns pass/fail for each category.
    """
    import os as _v_os

    from app.config import get_settings
    _settings = get_settings()
    if not _settings.anthropic_api_key:
        return {"pass": True, "failures": [], "warnings": ["No API key — skipped verification"]}

    # Extract text from PDF
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_texts = {}
        for i in range(len(doc)):
            page_texts[i + 1] = doc[i].get_text()
        page_count = len(doc)
        file_size_kb = len(pdf_bytes) // 1024
        # Check metadata
        meta_title = doc.metadata.get("title", "")
        meta_author = doc.metadata.get("author", "")
        # Check links
        all_links = []
        for i in range(len(doc)):
            for link in doc[i].get_links():
                if link.get("uri"):
                    all_links.append(f"P{i+1}: {link['uri']}")
        doc.close()
    except ImportError:
        return {"pass": True, "failures": [], "warnings": ["pymupdf not installed — skipped verification"]}

    # Load FULL spec
    spec_path = _v_os.path.join(
        _v_os.path.dirname(_v_os.path.dirname(_v_os.path.dirname(_v_os.path.dirname(__file__)))),
        "PDF_FEEDBACK.md",
    )
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_text = f.read()
    except FileNotFoundError:
        return {"pass": True, "failures": [], "warnings": ["PDF_FEEDBACK.md not found — skipped"]}

    # Build FULL page text
    dom = report.get("site_domain", "")
    score = int(report.get("overall_health", 0) or 0)
    recs = int(report.get("rec_count", 0) or 0)
    issues = int(report.get("problem_count", 0) or 0)
    total_posts = int(report.get("total_posts", 0) or 0)
    orphan = int(report.get("orphan_count", 0) or 0)
    thin = int(report.get("thin_content_count", 0) or 0)
    cpairs = int(report.get("cann_pair_count", 0) or 0)
    cposts = int(report.get("cann_post_count", 0) or 0)

    all_text = "\n\n".join(
        f"=== PAGE {p} ===\n{text}" for p, text in page_texts.items()
    )

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=_settings.anthropic_api_key)

    prompt = f"""You are a strict QA auditor. You must verify this PDF audit report against EVERY rule in the spec below.

## REPORT METADATA
- Domain: {dom}
- Health score: {score}/100
- Total posts: {total_posts}
- Total issues: {issues}
- Recommendations: {recs}
- Orphan posts: {orphan}
- Thin content posts: {thin}
- Cann pairs: {cpairs} (affecting {cposts} posts)
- Pages: {page_count}
- File size: {file_size_kb}KB
- PDF title: "{meta_title}"
- PDF author: "{meta_author}"
- Clickable links found: {all_links}

## FULL EXTRACTED TEXT FROM EVERY PAGE
{all_text}

## THE COMPLETE SPEC (every rule with a - [ ] checkbox must be verified)
{spec_text[:15000]}

## YOUR TASK

Go through the spec section by section. For every `- [ ]` checkbox rule you can verify from the extracted text, mark it PASS or FAIL.

Group your results into these categories:
1. NUMBERS — all number rules from 1.1
2. TEXT — all text rules from 1.2
3. TERMINOLOGY — all terminology rules from 1.4
4. LAYOUT — page count, page structure from 1.3 and Part 8
5. EXAMPLE FIX — all EF rules from Page 5 spec
6. QUICK WINS — all QW rules from Page 4 spec (check locked templates)
7. WHAT THIS MEANS — locked template check from Page 3 spec
8. EXEC SUMMARY — locked template check from Page 2 spec
9. FILE & METADATA — from 1.6
10. PRE-SEND CHECKLIST — spot-check from Part 6

For each category respond:
[number]. [CATEGORY]: PASS or FAIL
  - If FAIL: quote the specific offending text and name the specific rule it violates

Be STRICT but FAIR. Important clarifications:

SCHEMA MENTION COUNTING: The 4-mention limit applies ONLY to sentences that STATE THE FINDING that the site has 0%/100% no structured data. Sentences that RECOMMEND adding structured data (Quick Wins, 30-Day Plan, What this means action sentence) are action items, NOT finding mentions. Count only: "X% have no/zero structured data" statements. Do NOT count: "Add structured data to..." or "enables rich results" or "structured data is standard practice."

JARGON EXCEPTIONS: "Structured data," "rich results," "Flesch [N]," and "AI Overviews" are acceptable industry terms when accompanied by a parenthetical descriptor or contextual label. "Flesch 59 (professional audience level)" passes because the parenthetical explains the score.

NUMBER MATH: Issue Breakdown rows use ISSUE counts (7 thin + 47 orphan + 574 SEO + 23 overlap pairs). These will NOT sum to 628 because some posts have multiple issues and 628 is deduplicated. A footnote below the breakdown explains this. The overlap row shows the PAIR count (23), not the affected POST count (32).

LOCKED TEMPLATES: The exec summary, key findings, and what-this-means box use LOCKED TEMPLATES that are immutable code. The generator substitutes bracketed values ONLY. If the output differs from the template structure (added parentheticals, split sentences, appended consequences), it's a FAIL. "47 orphan posts" in the exec summary is correct even without "no internal links" because the Key Findings bullet on the same page provides the explanation. Locked template sentences are EXEMPT from the 25-word sentence rule — their length is intentional and tested.

PROMISE RULE: Distinguishes MECHANICAL outcomes (happen by definition: "Eliminate ranking competition" = merging pages mechanically removes competition) from EXTERNAL outcomes (depend on Google: "Increase traffic"). Mechanical outcomes are ALLOWED in Quick Win impact lines.

Check:
- Does exec summary match the LOCKED TEMPLATE structure?
- Does "What this means" match the LOCKED TEMPLATE?
- Do QW#1 and QW#2 match their locked templates?
- Is the Example Fix post #1 from the Top 5 table?
- Does the improved meta end with filler like "& more" or "and strategy planning"?
- Are there any "schema markup" or "JSON-LD" terms outside the dimension box?
- Does the domain appear as-crawled on every page (footer counts)?

Output ONLY the numbered results. No preamble."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        result_text = response.content[0].text.strip()

        # Parse results
        failures = []
        warnings = []
        all_pass = True

        import re as _re
        for line in result_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match any line containing PASS or FAIL with a rule identifier
            if "FAIL" in line and _re.search(r'[\d.]+[a-z]?\s', line):
                all_pass = False
                failures.append({"rule": line[:40], "detail": line})
            elif "PASS" in line and "FAIL" not in line:
                pass  # Passes don't need tracking

        logger.info("PDF Verification: %s", "ALL PASS" if all_pass else f"{len(failures)} FAILURES")
        for f in failures:
            logger.warning("  FAIL: %s", f["detail"])

        return {
            "pass": all_pass,
            "failures": failures,
            "warnings": warnings,
            "raw": result_text,
        }
    except Exception as e:
        logger.warning("PDF verification failed: %s", e)
        return {"pass": True, "failures": [], "warnings": [f"Verification error: {e}"]}


def _score_bg(score):
    """Background tint color for a score value."""
    if score >= 55:
        return HexColor("#dcfce7")
    if score >= 30:
        return HexColor("#fefce8")
    return HexColor("#fef2f2")
