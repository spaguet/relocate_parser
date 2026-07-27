"""Structured logging with secret redaction and correlation id binding."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

SECRET_FIELD_PATTERN = re.compile(
    r"(password|secret|token|api_key|apikey|authorization|session|credential)",
    re.IGNORECASE,
)

REDACTED = "***REDACTED***"


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    if SECRET_FIELD_PATTERN.search(key):
        return REDACTED
    if isinstance(value, str) and len(value) > 8 and SECRET_FIELD_PATTERN.search(value):
        return REDACTED
    return value


def redact_secrets_processor(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that masks sensitive fields in log events."""
    return {key: _redact_value(key, value) for key, value in event_dict.items()}


def configure_logging(*, log_level: str, json_logs: bool) -> None:
    """Configure structlog and stdlib logging for the application."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_secrets_processor,  # type: ignore[list-item]
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level.upper())

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
