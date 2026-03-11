"""Tests for encryption roundtrip and error cases."""

import pytest
from unittest.mock import patch, MagicMock
from app.utils.encryption import encrypt_value, decrypt_value, _get_fernet


class TestEncryption:
    """Encryption utility tests."""

    def test_roundtrip_basic(self):
        """Encrypt then decrypt should return original text."""
        plaintext = "my-secret-password"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_roundtrip_unicode(self):
        """Handle unicode content correctly."""
        plaintext = "pässwörd-ñoño-日本語"
        ciphertext = encrypt_value(plaintext)
        assert decrypt_value(ciphertext) == plaintext

    def test_roundtrip_long_string(self):
        """Handle long strings."""
        plaintext = "x" * 10000
        ciphertext = encrypt_value(plaintext)
        assert decrypt_value(ciphertext) == plaintext

    def test_empty_string_passthrough(self):
        """Empty strings should pass through unchanged."""
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_none_passthrough(self):
        """None-ish values should pass through."""
        assert encrypt_value(None) is None
        assert decrypt_value(None) is None

    def test_different_encryptions_differ(self):
        """Same plaintext encrypted twice should produce different ciphertexts (Fernet includes timestamp)."""
        a = encrypt_value("same-text")
        b = encrypt_value("same-text")
        assert a != b  # Fernet is non-deterministic

    def test_wrong_key_fails(self):
        """Decrypting with wrong key should raise ValueError."""
        ciphertext = encrypt_value("secret")
        # Patch settings to use a different key
        mock_settings = MagicMock()
        mock_settings.secret_key = "completely-different-key"
        with patch("app.utils.encryption.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="Decryption failed"):
                decrypt_value(ciphertext)

    def test_corrupted_ciphertext_fails(self):
        """Corrupted ciphertext should raise ValueError."""
        with pytest.raises(Exception):
            decrypt_value("not-a-valid-fernet-token")

    def test_fernet_key_deterministic(self):
        """Same SECRET_KEY should produce same Fernet key."""
        f1 = _get_fernet()
        f2 = _get_fernet()
        # Both should be able to decrypt each other's output
        ct = f1.encrypt(b"test")
        assert f2.decrypt(ct) == b"test"
