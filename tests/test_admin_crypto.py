"""Tests for sync_config encryption helpers."""

from __future__ import annotations

from pydantic import SecretStr

from relocate_helper.admin.crypto import (
    decrypt_sync_config,
    encrypt_sync_config,
    redact_sync_config,
)


def test_encrypt_and_decrypt_sync_config() -> None:
    secret = SecretStr("test-secret-key")
    original = {"username": "bot", "api_token": "super-secret", "channel": "@news"}
    encrypted = encrypt_sync_config(original, secret)
    assert encrypted is not None
    assert encrypted["api_token"] != "super-secret"
    assert encrypted["channel"] == "@news"

    decrypted = decrypt_sync_config(encrypted, secret)
    assert decrypted is not None
    assert decrypted["api_token"] == "super-secret"


def test_redact_sync_config() -> None:
    secret = SecretStr("test-secret-key")
    encrypted = encrypt_sync_config({"api_token": "hidden"}, secret)
    redacted = redact_sync_config(encrypted)
    assert redacted == {"api_token": "***"}
