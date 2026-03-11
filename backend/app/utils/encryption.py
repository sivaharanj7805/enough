"""Encryption utilities for sensitive database fields.

Uses Fernet symmetric encryption (AES-128-CBC) derived from the app SECRET_KEY.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the app SECRET_KEY."""
    settings = get_settings()
    # Derive a 32-byte key from SECRET_KEY via SHA256, then base64 encode for Fernet
    key_bytes = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt an encrypted string value."""
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or wrong key")
        raise ValueError("Decryption failed: invalid key or corrupted data")
