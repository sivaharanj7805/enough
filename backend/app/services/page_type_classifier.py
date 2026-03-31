"""Auto-classify page types from URL patterns and HTML structure.

Detects: blog, product, documentation, landing, glossary, index.
Used by health scoring and problem detection to apply content-type-specific thresholds.
"""

import re
from urllib.parse import urlparse


# URL pattern rules (checked in order, first match wins)
_URL_PATTERNS: list[tuple[str, list[str]]] = [
    ("product", ["/product/", "/products/", "/shop/", "/store/", "/p/", "/item/"]),
    ("documentation", ["/docs/", "/doc/", "/api/", "/reference/", "/changelog/", "/sdk/", "/guide/"]),
    ("glossary", ["/glossary/", "/terms/", "/definitions/", "/what-is-", "/what-is/"]),
    ("landing", ["/features", "/pricing", "/enterprise", "/solutions/"]),
    ("index", ["/category/", "/tag/", "/tags/", "/archive/", "/page/"]),
]

# Schema.org @type → page_type mapping
_SCHEMA_TYPE_MAP: dict[str, str] = {
    "Product": "product",
    "SoftwareApplication": "product",
    "TechArticle": "documentation",
    "APIReference": "documentation",
    "FAQPage": "blog",
    "HowTo": "blog",
    "Recipe": "blog",
    "Article": "blog",
    "BlogPosting": "blog",
    "NewsArticle": "blog",
}


def classify_page_type(url: str, body_html: str = "", headings: list | None = None) -> str:
    """Classify a page's type from URL patterns, schema markup, and HTML structure.

    Returns one of: 'blog', 'product', 'documentation', 'landing', 'glossary', 'index'
    """
    path = urlparse(url).path.lower()
    html_lower = body_html.lower() if body_html else ""

    # 1. Check URL patterns
    for page_type, patterns in _URL_PATTERNS:
        if any(pat in path for pat in patterns):
            return page_type

    # 2. Check Schema.org @type in JSON-LD
    if body_html:
        schema_matches = re.findall(r'"@type"\s*:\s*"([^"]+)"', body_html)
        for schema_type in schema_matches:
            if schema_type in _SCHEMA_TYPE_MAP:
                return _SCHEMA_TYPE_MAP[schema_type]

    # 3. HTML structure heuristics
    if body_html:
        # Product signals: price elements, add-to-cart
        if any(s in html_lower for s in [
            'class="price"', 'class="product-price"', "add-to-cart",
            "add to cart", "buy now", 'itemprop="price"',
        ]):
            return "product"

        # Documentation signals: lots of code blocks
        code_count = html_lower.count("<pre") + html_lower.count("<code")
        if code_count >= 3:
            return "documentation"

        # Index/archive: mostly links, very little text
        if headings and len(headings) <= 1:
            link_count = html_lower.count("<a ")
            if link_count > 20 and len(body_html) < 5000:
                return "index"

    # 4. Landing page: very short path (/, /about, /contact)
    stripped = path.strip("/")
    if stripped in ("", "about", "contact", "team", "careers", "privacy", "terms"):
        return "landing"

    # Default
    return "blog"
