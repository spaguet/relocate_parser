"""Telegram ingestion public API."""

from relocate_helper.ingestion.telegram.adapter import (
    FakeTelegramClient,
    TelegramClientAdapter,
    TelegramMediaMeta,
    TelegramMessage,
    TelegramPage,
    TelegramPeer,
)
from relocate_helper.ingestion.telegram.sync import (
    TelegramSyncRequest,
    TelegramSyncResult,
    TelegramSyncService,
    build_job_idempotency_key,
    document_idempotency_key,
)
from relocate_helper.ingestion.telegram.tasks import enqueue_telegram_sync, run_telegram_sync_job

__all__ = [
    "FakeTelegramClient",
    "TelegramClientAdapter",
    "TelegramMediaMeta",
    "TelegramMessage",
    "TelegramPage",
    "TelegramPeer",
    "TelegramSyncRequest",
    "TelegramSyncResult",
    "TelegramSyncService",
    "build_job_idempotency_key",
    "document_idempotency_key",
    "enqueue_telegram_sync",
    "run_telegram_sync_job",
]
