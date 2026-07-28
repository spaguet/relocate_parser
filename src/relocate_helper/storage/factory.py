"""Object storage factory helpers."""

from __future__ import annotations

from relocate_helper.common.config import AppEnv, Settings
from relocate_helper.storage.memory import InMemoryObjectStorage
from relocate_helper.storage.protocol import ObjectStorage
from relocate_helper.storage.s3 import S3ObjectStorage


def create_object_storage(settings: Settings) -> ObjectStorage:
    """Return S3 backend in normal environments; in-memory for tests."""
    if settings.app_env == AppEnv.TEST:
        return InMemoryObjectStorage()
    return S3ObjectStorage(settings=settings)
