"""Encrypt/decrypt sensitive fields in source sync_config."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

# Keys in sync_config that must never appear in plaintext at rest.
SENSITIVE_SYNC_CONFIG_KEYS = frozenset(
    {
        "api_token",
        "bot_token",
        "password",
        "session_string",
        "api_hash",
        "access_token",
        "refresh_token",
        "secret",
    }
)

ENCRYPTED_PREFIX = "enc:v1:"


def _fernet(secret: SecretStr) -> Fernet:
    digest = hashlib.sha256(secret.get_secret_value().encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_sync_config(
    sync_config: dict[str, Any] | None,
    secret: SecretStr,
) -> dict[str, Any] | None:
    """Return sync_config copy with sensitive values encrypted."""
    if not sync_config:
        return sync_config

    fernet = _fernet(secret)
    encrypted: dict[str, Any] = {}
    for key, value in sync_config.items():
        if key in SENSITIVE_SYNC_CONFIG_KEYS and value is not None:
            token = fernet.encrypt(str(value).encode()).decode()
            encrypted[key] = f"{ENCRYPTED_PREFIX}{token}"
        else:
            encrypted[key] = value
    return encrypted


def decrypt_sync_config(
    sync_config: dict[str, Any] | None,
    secret: SecretStr,
) -> dict[str, Any] | None:
    """Decrypt sensitive sync_config values for internal use only."""
    if not sync_config:
        return sync_config

    fernet = _fernet(secret)
    decrypted: dict[str, Any] = {}
    for key, value in sync_config.items():
        if (
            key in SENSITIVE_SYNC_CONFIG_KEYS
            and isinstance(value, str)
            and value.startswith(ENCRYPTED_PREFIX)
        ):
            token = value.removeprefix(ENCRYPTED_PREFIX).encode()
            try:
                decrypted[key] = fernet.decrypt(token).decode()
            except InvalidToken:
                decrypted[key] = None
        else:
            decrypted[key] = value
    return decrypted


def redact_sync_config(sync_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return sync_config safe for admin API responses."""
    if not sync_config:
        return sync_config

    redacted: dict[str, Any] = {}
    for key, value in sync_config.items():
        if key in SENSITIVE_SYNC_CONFIG_KEYS:
            redacted[key] = "***" if value is not None else None
        else:
            redacted[key] = value
    return redacted


def sync_config_has_secrets(sync_config: dict[str, Any] | None) -> bool:
    if not sync_config:
        return False
    return any(key in SENSITIVE_SYNC_CONFIG_KEYS and sync_config.get(key) for key in sync_config)
