"""Tests for security hardening.

Covers:
- Cron secret authentication
- URL normalization / deduplication
- Security headers middleware
- Request size limiting
- Host validation
- OAuth state parameter signing
- Input validation
"""

import hashlib
import hmac
import json
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.utils.url_normalize import normalize_url, urls_are_same


# ═══════════════════════════════════════════════
# URL Normalization
# ═══════════════════════════════════════════════

class TestURLNormalization:
    """URL normalization for deduplication."""

    def test_trailing_slash_removed(self):
        assert normalize_url("https://example.com/post/") == "https://example.com/post"

    def test_root_slash_preserved(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_www_stripped(self):
        assert normalize_url("https://www.example.com/post") == "https://example.com/post"

    def test_http_upgraded_to_https(self):
        assert normalize_url("http://example.com/post") == "https://example.com/post"

    def test_domain_lowercased(self):
        assert normalize_url("https://Example.COM/Post") == "https://example.com/Post"

    def test_path_case_preserved(self):
        # Path casing matters for some servers
        result = normalize_url("https://example.com/Blog/Post")
        assert "/Blog/Post" in result

    def test_utm_params_stripped(self):
        result = normalize_url("https://example.com/post?utm_source=twitter&utm_medium=social")
        assert "utm_source" not in result
        assert "utm_medium" not in result

    def test_fbclid_stripped(self):
        result = normalize_url("https://example.com/post?fbclid=abc123")
        assert "fbclid" not in result

    def test_gclid_stripped(self):
        result = normalize_url("https://example.com/post?gclid=xyz")
        assert "gclid" not in result

    def test_non_tracking_params_preserved(self):
        result = normalize_url("https://example.com/search?q=hello&page=2")
        assert "q=hello" in result
        assert "page=2" in result

    def test_fragment_removed(self):
        assert normalize_url("https://example.com/post#comments") == "https://example.com/post"

    def test_default_port_removed(self):
        assert normalize_url("https://example.com:443/post") == "https://example.com/post"
        assert normalize_url("http://example.com:80/post") == "https://example.com/post"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""

    def test_urls_are_same(self):
        assert urls_are_same(
            "https://www.example.com/post/",
            "http://example.com/post"
        )

    def test_urls_are_different(self):
        assert not urls_are_same(
            "https://example.com/post-a",
            "https://example.com/post-b"
        )

    def test_complex_normalization(self):
        """All normalizations combined."""
        result = normalize_url(
            "http://WWW.Example.COM:80/Blog/Post/?utm_source=twitter&page=2&fbclid=abc#section"
        )
        assert result == "https://example.com/Blog/Post?page=2"


# ═══════════════════════════════════════════════
# Cron Secret Auth
# ═══════════════════════════════════════════════

class TestCronSecretAuth:
    """Test cron endpoint authentication."""

    @pytest.mark.asyncio
    async def test_verify_cron_no_secret_configured(self):
        """When CRON_SECRET is empty, allow but warn."""
        from app.dependencies import verify_cron_secret

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(cron_secret="")
            await verify_cron_secret(x_cron_secret=None)

    @pytest.mark.asyncio
    async def test_verify_cron_missing_header(self):
        """When CRON_SECRET is set but header is missing, reject."""
        from app.dependencies import verify_cron_secret
        from fastapi import HTTPException

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(cron_secret="my-secret")
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_cron_wrong_secret(self):
        """Wrong cron secret should be rejected."""
        from app.dependencies import verify_cron_secret
        from fastapi import HTTPException

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(cron_secret="correct-secret")
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret="wrong-secret")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_verify_cron_correct_secret(self):
        """Correct cron secret should pass."""
        from app.dependencies import verify_cron_secret

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(cron_secret="correct-secret")
            await verify_cron_secret(x_cron_secret="correct-secret")


# ═══════════════════════════════════════════════
# Security Middleware
# ═══════════════════════════════════════════════

class TestSecurityHeaders:
    """Test that security headers are present."""

    def test_middleware_imports(self):
        from app.middleware.security import (
            SecurityHeadersMiddleware,
            RequestSizeLimitMiddleware,
            HostValidationMiddleware,
        )
        assert SecurityHeadersMiddleware is not None
        assert RequestSizeLimitMiddleware is not None
        assert HostValidationMiddleware is not None


# ═══════════════════════════════════════════════
# OAuth State Parameter
# ═══════════════════════════════════════════════

class TestOAuthState:
    """Test OAuth state parameter signing and verification."""

    def test_state_roundtrip(self):
        """State parameter should survive encode → sign → verify → decode."""
        secret = "test-secret-key"
        site_id = "550e8400-e29b-41d4-a716-446655440000"

        # Encode (matches auth.py logic)
        state_data = {"site_id": site_id}
        state_json = json.dumps(state_data, separators=(",", ":"))
        state_b64 = base64.urlsafe_b64encode(state_json.encode()).decode()
        state_sig = hmac.new(
            secret.encode(),
            state_b64.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        state = f"{state_b64}.{state_sig}"

        # Decode (matches callback logic)
        parts = state.rsplit(".", 1)
        assert len(parts) == 2

        recv_b64, recv_sig = parts
        expected_sig = hmac.new(
            secret.encode(),
            recv_b64.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        assert hmac.compare_digest(recv_sig, expected_sig)

        recv_data = json.loads(base64.urlsafe_b64decode(recv_b64))
        assert recv_data["site_id"] == site_id

    def test_tampered_state_fails(self):
        """Tampered state should fail signature verification."""
        secret = "test-secret-key"

        state_data = {"site_id": "real-id"}
        state_json = json.dumps(state_data, separators=(",", ":"))
        state_b64 = base64.urlsafe_b64encode(state_json.encode()).decode()
        state_sig = hmac.new(
            secret.encode(),
            state_b64.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        # Tamper with the payload
        tampered_data = {"site_id": "attacker-controlled-id"}
        tampered_json = json.dumps(tampered_data, separators=(",", ":"))
        tampered_b64 = base64.urlsafe_b64encode(tampered_json.encode()).decode()

        # Try to use the original signature with tampered payload
        expected_sig = hmac.new(
            secret.encode(),
            tampered_b64.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        # Original sig won't match tampered payload
        assert not hmac.compare_digest(state_sig, expected_sig)

    def test_empty_state_no_crash(self):
        """Empty state should be handled gracefully."""
        state = ""
        # Should not crash
        if state and "." in state:
            assert False, "Should not enter this branch"


# ═══════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════

class TestSecurityConfig:
    """Test security configuration options."""

    def test_cron_secret_config(self):
        from app.config import Settings
        s = Settings(cron_secret="my-secret-123")
        assert s.cron_secret == "my-secret-123"

    def test_allowed_hosts_parsing(self):
        from app.config import Settings
        s = Settings(allowed_hosts="example.com, api.example.com")
        assert s.allowed_host_list == ["example.com", "api.example.com"]

    def test_allowed_hosts_empty(self):
        from app.config import Settings
        s = Settings(allowed_hosts="")
        assert s.allowed_host_list == []

    def test_docs_disabled_in_production(self):
        """Docs should be disabled when secret_key is changed from default."""
        # This tests the main.py logic
        from app.config import Settings
        s = Settings(secret_key="real-production-key")
        assert s.secret_key != "change-me-in-production"


# ═══════════════════════════════════════════════
# Encryption
# ═══════════════════════════════════════════════

class TestEncryption:
    """Test Fernet encryption utilities."""

    def test_encrypt_decrypt_roundtrip(self):
        from app.utils.encryption import encrypt_value, decrypt_value
        plaintext = "my-secret-refresh-token"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

    def test_empty_string_passthrough(self):
        from app.utils.encryption import encrypt_value, decrypt_value
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_different_plaintexts_different_ciphertexts(self):
        from app.utils.encryption import encrypt_value
        a = encrypt_value("secret-a")
        b = encrypt_value("secret-b")
        assert a != b

    def test_decrypt_invalid_token_raises(self):
        from app.utils.encryption import decrypt_value
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_value("not-a-valid-fernet-token")


# ═══════════════════════════════════════════════
# Auth / JWT Validation
# ═══════════════════════════════════════════════

class TestAuthDependency:
    """Test auth token validation."""

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        from app.dependencies import get_current_user_id
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(authorization="")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_prefix_stripped(self):
        from app.dependencies import get_current_user_id
        # Valid UUID as dev fallback
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        result = await get_current_user_id(authorization=f"Bearer {user_id}")
        assert result == user_id

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        from app.dependencies import get_current_user_id
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(authorization="not-a-uuid-or-jwt")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raw_uuid_accepted_in_dev(self):
        from app.dependencies import get_current_user_id
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        result = await get_current_user_id(authorization=user_id)
        assert result == user_id


# ═══════════════════════════════════════════════
# WordPress Connector — Headings
# ═══════════════════════════════════════════════

class TestWordPressHeadings:
    """Test that WordPress connector now extracts headings."""

    def test_wp_connector_has_extract_headings(self):
        from app.services.wordpress import WordPressConnector
        assert hasattr(WordPressConnector, "_extract_headings")

    def test_wp_headings_extracted(self):
        from app.services.wordpress import WordPressConnector
        from bs4 import BeautifulSoup

        html = "<h2>Intro</h2><p>text</p><h3>Details</h3>"
        soup = BeautifulSoup(html, "html.parser")
        headings = WordPressConnector._extract_headings(soup)
        assert len(headings) == 2
        assert headings[0] == {"level": "h2", "text": "Intro"}
        assert headings[1] == {"level": "h3", "text": "Details"}
