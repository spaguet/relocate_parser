"""PostgreSQL-backed enum types for the data model."""

from __future__ import annotations

import enum


class PublicationStatus(str, enum.Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    HIDDEN = "hidden"


class SourceType(str, enum.Enum):
    TELEGRAM = "telegram"
    WEB = "web"
    YOUTUBE = "youtube"
    FILE = "file"
    FORUM = "forum"
    OTHER = "other"


class SourceStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"


class DocumentStatus(str, enum.Enum):
    ACTIVE = "active"
    DELETED_AT_SOURCE = "deleted_at_source"
    REDACTED = "redacted"
    QUARANTINED = "quarantined"


class ChunkStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class IngestionJobType(str, enum.Enum):
    INITIAL_IMPORT = "initial_import"
    INCREMENTAL_SYNC = "incremental_sync"
    REPROCESS = "reprocess"
    MANUAL_UPLOAD = "manual_upload"


class IngestionJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelRunPurpose(str, enum.Enum):
    CLASSIFY = "classify"
    EXTRACT = "extract"
    EMBED = "embed"
    ANSWER = "answer"
    RERANK = "rerank"
    OTHER = "other"


class FactType(str, enum.Enum):
    PRICE = "price"
    ADDRESS = "address"
    INSTRUCTION = "instruction"
    RECOMMENDATION = "recommendation"
    ORGANIZATION = "organization"
    OTHER = "other"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class UsageEventType(str, enum.Enum):
    QUERY = "query"
    ANSWER = "answer"
    LIMIT_HIT = "limit_hit"
    CACHE_HIT = "cache_hit"
    OTHER = "other"


class FeedbackRating(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class TombstoneEntityType(str, enum.Enum):
    DOCUMENT = "document"
    DOCUMENT_VERSION = "document_version"
    CHUNK = "chunk"
    FACT = "fact"
    USER_DATA = "user_data"
    OTHER = "other"


class ValidityPeriodType(str, enum.Enum):
    POINT = "point"
    RANGE = "range"
    UNKNOWN = "unknown"
