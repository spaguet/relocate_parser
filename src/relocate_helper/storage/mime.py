"""MIME type validation by content sniffing and extension."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

import filetype

from relocate_helper.storage.exceptions import QuarantinedContentError, UnsupportedContentError

# Extensions we accept when MIME sniffing is inconclusive (plain text family).
TEXT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".csv", ".tsv", ".log"})

# MIME types allowed for ingestion (non-quarantine).
ALLOWED_MIME_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/pdf",
        "application/zip",
        "application/gzip",
        "application/x-gzip",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "audio/mpeg",
        "audio/ogg",
        "video/mp4",
        "video/webm",
    }
)

# Active or dangerous content — store in quarantine, do not process.
QUARANTINE_MIME_TYPES = frozenset(
    {
        "text/html",
        "application/javascript",
        "text/javascript",
        "application/x-javascript",
        "application/x-sh",
        "application/x-msdownload",
        "application/vnd.microsoft.portable-executable",
        "application/x-msdos-program",
        "application/x-dosexec",
        "image/svg+xml",
        "application/xhtml+xml",
    }
)

QUARANTINE_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".js",
        ".mjs",
        ".sh",
        ".bat",
        ".cmd",
        ".exe",
        ".dll",
        ".svg",
        ".php",
        ".jsp",
        ".asp",
        ".aspx",
    }
)


@dataclass(frozen=True, slots=True)
class MimeValidationResult:
    mime_type: str
    quarantined: bool
    reason: str | None = None


def _extension(filename: str | None) -> str:
    if not filename:
        return ""
    return PurePath(filename).suffix.lower()


def _sniff_mime(data: bytes) -> str | None:
    kind = filetype.guess(data)
    if kind is not None:
        return str(kind.mime)
    sample = data[:4096]
    if sample and not sample.strip(b"\x00"):
        try:
            sample.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return None
    return None


def validate_content(
    data: bytes,
    *,
    filename: str | None = None,
    allowed_mime_types: frozenset[str] | None = None,
) -> MimeValidationResult:
    """Validate MIME by magic bytes and extension; flag quarantine candidates."""
    allowed = allowed_mime_types or ALLOWED_MIME_TYPES
    ext = _extension(filename)
    sniffed = _sniff_mime(data)

    if ext in QUARANTINE_EXTENSIONS:
        mime = sniffed or "application/octet-stream"
        return MimeValidationResult(mime_type=mime, quarantined=True, reason=f"extension:{ext}")

    if sniffed in QUARANTINE_MIME_TYPES:
        return MimeValidationResult(
            mime_type=sniffed,
            quarantined=True,
            reason=f"mime:{sniffed}",
        )

    if sniffed is not None:
        if sniffed in allowed:
            return MimeValidationResult(mime_type=sniffed, quarantined=False)
        if sniffed in QUARANTINE_MIME_TYPES:
            return MimeValidationResult(
                mime_type=sniffed,
                quarantined=True,
                reason=f"mime:{sniffed}",
            )
        raise UnsupportedContentError(f"Unsupported MIME type: {sniffed}")

    if ext in TEXT_EXTENSIONS:
        return MimeValidationResult(mime_type="text/plain", quarantined=False)

    raise UnsupportedContentError(
        f"Could not determine allowed MIME type (extension={ext or 'none'})"
    )


def ensure_not_quarantined(result: MimeValidationResult) -> None:
    if result.quarantined:
        raise QuarantinedContentError(result.reason or "content quarantined")
