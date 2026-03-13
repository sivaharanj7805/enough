"""URL normalization for deduplication.

Handles common URL variations that point to the same content:
- www vs non-www
- Trailing slashes
- Protocol (http vs https)
- Query parameter stripping (utm_, fbclid, etc.)
- Fragment removal
- Case normalization of domain
"""

import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

# Query parameters that are tracking/marketing noise (not content identifiers)
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "msclkid", "dclid",
    "mc_cid", "mc_eid",
    "ref", "source", "referrer",
    "_ga", "_gl",
    "hsCtaTracking",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to a canonical form for deduplication.

    Examples:
        https://www.example.com/blog/post/ → https://example.com/blog/post
        http://Example.COM/Blog/Post?utm_source=twitter → https://example.com/Blog/Post
        https://example.com/post#comments → https://example.com/post
    """
    if not url:
        return url

    parsed = urlparse(url)

    # Normalize scheme to https
    scheme = "https"

    # Normalize domain: lowercase, strip www
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove default ports
    if netloc.endswith(":443") or netloc.endswith(":80"):
        netloc = netloc.rsplit(":", 1)[0]

    # Normalize path: remove trailing slash (but keep root /)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Normalize empty path to /
    if not path:
        path = "/"

    # Strip tracking query parameters
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered_params = {
        k: v for k, v in query_params.items()
        if k.lower() not in STRIP_PARAMS
    }

    # Sort remaining params for consistency
    query = urlencode(sorted(filtered_params.items()), doseq=True) if filtered_params else ""

    # Remove fragment
    fragment = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def urls_are_same(url1: str, url2: str) -> bool:
    """Check if two URLs point to the same content after normalization."""
    return normalize_url(url1) == normalize_url(url2)
