"""Domain events emitted by ingestion pipelines for downstream processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentCreated:
    document_id: int
    source_id: int
    external_id: str


@dataclass(frozen=True, slots=True)
class DocumentChanged:
    document_id: int
    source_id: int
    external_id: str
    version_id: int


@dataclass(frozen=True, slots=True)
class DocumentDeleted:
    document_id: int
    source_id: int
    external_id: str


IngestionEvent = DocumentCreated | DocumentChanged | DocumentDeleted
