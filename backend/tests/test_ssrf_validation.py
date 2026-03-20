"""Tests for SSRF prevention in site URL validation."""

import pytest
from fastapi import HTTPException

from app.routers.sites import _validate_url_not_internal


class TestSSRFPrevention:
    """Ensure internal/private URLs are rejected."""

    def test_public_url_allowed(self):
        """Normal public URLs should pass."""
        _validate_url_not_internal("https://example.com", "test_url")

    def test_public_url_with_path(self):
        """Public URLs with paths should pass."""
        _validate_url_not_internal("https://example.com/sitemap.xml", "test_url")

    def test_localhost_rejected(self):
        """localhost should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://localhost:8000/admin", "test_url")
        assert exc.value.status_code == 422

    def test_loopback_ip_rejected(self):
        """127.0.0.1 should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://127.0.0.1/api", "test_url")
        assert exc.value.status_code == 422

    def test_private_ip_rejected(self):
        """192.168.x.x should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://192.168.1.1/admin", "test_url")
        assert exc.value.status_code == 422

    def test_10_network_rejected(self):
        """10.x.x.x should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://10.0.0.1/internal", "test_url")
        assert exc.value.status_code == 422

    def test_172_private_rejected(self):
        """172.16.x.x should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://172.16.0.1/secret", "test_url")
        assert exc.value.status_code == 422

    def test_dot_local_rejected(self):
        """.local domains should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://myservice.local/api", "test_url")
        assert exc.value.status_code == 422

    def test_ftp_scheme_rejected(self):
        """Non-HTTP schemes should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("ftp://example.com/file", "test_url")
        assert exc.value.status_code == 422

    def test_none_url_allowed(self):
        """None URL should be silently allowed (optional field)."""
        _validate_url_not_internal(None, "test_url")

    def test_empty_url_allowed(self):
        """Empty string should be silently allowed."""
        _validate_url_not_internal("", "test_url")

    def test_link_local_rejected(self):
        """169.254.x.x link-local addresses should be rejected."""
        with pytest.raises(HTTPException) as exc:
            _validate_url_not_internal("http://169.254.1.1/metadata", "test_url")
        assert exc.value.status_code == 422
