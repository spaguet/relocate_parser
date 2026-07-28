"""Admin HTTP routes for sources and document metadata."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from relocate_helper.admin.schemas import (
    DeleteDocumentContentRequest,
    DocumentResponse,
    SourceCreateRequest,
    SourceResponse,
    SourceUpdateRequest,
)
from relocate_helper.admin.sources import (
    SourceCreateInput,
    SourceNotFoundError,
    SourceRegistryService,
    SourceUpdateInput,
)
from relocate_helper.api.dependencies import (
    get_db_session,
    get_deletion_service,
    get_source_registry,
)
from relocate_helper.db.enums import DocumentStatus, SourceStatus
from relocate_helper.db.models.documents import Document
from relocate_helper.db.models.sources import Source
from relocate_helper.storage.deletion import ContentDeletionService

router = APIRouter(prefix="/admin", tags=["admin"])

RegistryDep = Annotated[SourceRegistryService, Depends(get_source_registry)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
DeletionDep = Annotated[ContentDeletionService, Depends(get_deletion_service)]


def _source_response(source: Source, registry: SourceRegistryService) -> SourceResponse:
    data = SourceResponse.model_validate(source)
    return data.model_copy(update={"sync_config": registry.public_sync_config(source)})


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    registry: RegistryDep,
    session: SessionDep,
    city_id: int | None = None,
    status_filter: Annotated[SourceStatus | None, Query(alias="status")] = None,
) -> list[SourceResponse]:
    sources = await registry.list_sources(session, city_id=city_id, status=status_filter)
    return [_source_response(source, registry) for source in sources]


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreateRequest,
    registry: RegistryDep,
    session: SessionDep,
) -> SourceResponse:
    async with session.begin():
        source = await registry.create_source(
            session,
            SourceCreateInput(
                source_type=body.source_type,
                name=body.name,
                legal_basis=body.legal_basis,
                city_id=body.city_id,
                status=body.status,
                external_ref=body.external_ref,
                sync_config=body.sync_config,
                retention_policy=body.retention_policy,
            ),
        )
    await session.refresh(source)
    return _source_response(source, registry)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int,
    registry: RegistryDep,
    session: SessionDep,
) -> SourceResponse:
    try:
        source = await registry.get_source(session, source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _source_response(source, registry)


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    body: SourceUpdateRequest,
    registry: RegistryDep,
    session: SessionDep,
) -> SourceResponse:
    try:
        async with session.begin():
            source = await registry.update_source(
                session,
                source_id,
                SourceUpdateInput(
                    name=body.name,
                    legal_basis=body.legal_basis,
                    city_id=body.city_id,
                    status=body.status,
                    external_ref=body.external_ref,
                    sync_config=body.sync_config,
                    retention_policy=body.retention_policy,
                    sync_cursor=body.sync_cursor,
                    last_synced_at=body.last_synced_at,
                ),
            )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.refresh(source)
    return _source_response(source, registry)


@router.delete("/sources/{source_id}", response_model=SourceResponse)
async def disable_source(
    source_id: int,
    registry: RegistryDep,
    session: SessionDep,
) -> SourceResponse:
    try:
        async with session.begin():
            source = await registry.disable_source(session, source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.refresh(source)
    return _source_response(source, registry)


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    session: SessionDep,
    source_id: int | None = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DocumentResponse]:
    query = (
        select(Document)
        .options(selectinload(Document.current_version))
        .order_by(Document.id.desc())
        .limit(limit)
    )
    if source_id is not None:
        query = query.where(Document.source_id == source_id)
    if status_filter is not None:
        query = query.where(Document.status == status_filter)
    documents = list(await session.scalars(query))
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    session: SessionDep,
) -> DocumentResponse:
    document = await session.scalar(
        select(Document)
        .options(selectinload(Document.current_version))
        .where(Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(document)


@router.post("/documents/{document_id}/delete-content", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_content(
    document_id: int,
    body: DeleteDocumentContentRequest,
    session: SessionDep,
    deletion_service: DeletionDep,
) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    async with session.begin():
        await deletion_service.delete_document_content(
            session,
            document,
            reason=body.reason,
        )
