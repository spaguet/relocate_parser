"""Telegram ingestion errors."""

from __future__ import annotations


class TelegramIngestionError(Exception):
    """Base error for Telegram import."""


class TelegramSourceConfigError(TelegramIngestionError):
    """Source is missing required configuration or legal basis."""


class TelegramPeerResolveError(TelegramIngestionError):
    """Could not resolve username, link or peer id."""


class TelegramFloodWaitError(TelegramIngestionError):
    """Telegram rate limit — retry after delay."""

    def __init__(self, seconds: int, *, message: str = "FloodWait") -> None:
        self.seconds = seconds
        super().__init__(message)


class TelegramJobCancelledError(TelegramIngestionError):
    """Job was cancelled by administrator."""
