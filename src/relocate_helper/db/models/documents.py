"""Document and chunk models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import DEFAULT_EMBEDDING_DIMENSION, Base, TimestampMixin, VersionMixin
from relocate_helper.db.enums import ChunkStatus, DocumentStatus
from relocate_helper.db.types import JsonDict

if TYPE_CHECKING:
    from relocate_helper.db.models.knowledge import FactEvidence
    from relocate_helper.db.models.sources import Source


class Document(Base, TimestampMixin, VersionMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=False, length=32),
        nullable=False,
        server_default=DocumentStatus.ACTIVE.value,
    )
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    source: Mapped[Source] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
    )
    current_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[current_version_id],
        post_update=True,
    )

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_documents_source_external"),
        Index("ix_documents_source_status", "source_id", "status"),
        Index("ix_documents_city_status", "city_id", "status"),
    )


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document_version")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_doc_version"),
        CheckConstraint("version_number > 0", name="document_versions_version_positive"),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="document_versions_size_non_negative",
        ),
        Index("ix_document_versions_content_hash", "content_hash"),
    )


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ChunkStatus] = mapped_column(
        Enum(ChunkStatus, name="chunk_status", native_enum=False, length=32),
        nullable=False,
        server_default=ChunkStatus.ACTIVE.value,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIMENSION),
        nullable=True,
    )
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
        nullable=True,
    )
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")
    evidence_links: Mapped[list[FactEvidence]] = relationship(back_populates="chunk")

    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_chunks_document_version_index",
        ),
        CheckConstraint("chunk_index >= 0", name="chunks_index_non_negative"),
        Index("ix_chunks_document_version_status", "document_version_id", "status"),
        Index("ix_chunks_city_topic_status", "city_id", "topic_id", "status"),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )
