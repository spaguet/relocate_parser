"""Storage layer exceptions."""

from __future__ import annotations


class StorageError(Exception):
    """Base error for object storage operations."""


class ObjectNotFoundError(StorageError):
    """Requested object does not exist in storage."""


class ObjectTooLargeError(StorageError):
    """Uploaded content exceeds configured size limit."""


class UnsupportedContentError(StorageError):
    """Content type or extension is not allowed."""


class QuarantinedContentError(StorageError):
    """Content was rejected and placed in quarantine storage."""
