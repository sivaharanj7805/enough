"""SSRF protection — validate URLs and domains before outbound HTTP requests.

Used across routers and services to prevent Server-Side Request Forgery.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Blocked hostname patterns
_BLOCKED_HOSTNAMES = {"localhost", "::1"}
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")


def validate_url_not_internal(url: str | None, field_name: str = "url") -> None:
    """Raise ValueError if URL points to internal/private IP ranges.

    Checks:
    1. Scheme must be http or https
    2. IP-literal hostnames must not be private/loopback/link-local/reserved
    3. Known internal hostnames (localhost, .local, .internal) are blocked
    4. DNS resolution is checked to catch domains that resolve to internal IPs
    """
    if not url:
        return

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"{field_name}: only http/https URLs are allowed")

        if not hostname:
            raise ValueError(f"{field_name}: URL has no hostname")

        _check_hostname(hostname, field_name)

    except ValueError:
        raise
    except Exception as e:
        logger.warning("URL validation error for %s=%r: %s", field_name, url, e)
        raise ValueError(f"{field_name}: invalid URL")


def validate_domain_not_internal(domain: str, field_name: str = "domain") -> None:
    """Raise ValueError if a bare domain (no scheme) resolves to internal IPs.

    Use for inputs like competitor_domain that are domains, not full URLs.
    """
    if not domain:
        return

    # Strip any accidental scheme prefix
    if "://" in domain:
        domain = urlparse(domain).hostname or domain

    _check_hostname(domain, field_name)


def _check_hostname(hostname: str, field_name: str) -> None:
    """Core check — validates a hostname is not internal."""
    hostname_lower = hostname.lower()

    # Block known internal hostnames
    if hostname_lower in _BLOCKED_HOSTNAMES:
        raise ValueError(f"{field_name}: localhost is not allowed")

    if any(hostname_lower.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise ValueError(f"{field_name}: internal domains are not allowed")

    # Check if hostname is an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        _check_ip(ip, field_name)
        return  # It's a valid public IP literal — OK
    except ValueError:
        pass  # Not an IP literal — it's a hostname, continue to DNS check

    # DNS resolution check: resolve hostname and verify all IPs are public
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            _check_ip(ip, field_name)
    except socket.gaierror:
        # DNS resolution failed — the domain doesn't resolve.
        # Allow it through (the HTTP client will fail later with a clear error).
        pass
    except ValueError:
        raise


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, field_name: str) -> None:
    """Raise ValueError if IP is private/loopback/link-local/reserved."""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(
            f"{field_name}: requests to internal/private IP addresses are not allowed"
        )
