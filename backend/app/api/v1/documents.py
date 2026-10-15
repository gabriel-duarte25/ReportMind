from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage
from app.schemas.document import DocumentChunkResponse, DocumentPageResponse, DocumentResponse, IndexingStatusResponse, LibraryStatsResponse, ProcessingStatusResponse
from app.services.documents import delete_document, get_document_or_404, list_documents, save_document
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.indexing import claim_indexing, indexing_status, run_indexing
from app.services.processing import claim_processing, document_processing_status, library_stats, run_document_processing
from app.services.vector_store import VectorStore, get_vector_store

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    document = await save_document(file, db, settings)
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def documents(db: Annotated[Session, Depends(get_db)]) -> list[DocumentResponse]:
    return [DocumentResponse.model_validate(document) for document in list_documents(db)]


@router.get("/stats", response_model=LibraryStatsResponse)
def document_stats(db: Annotated[Session, Depends(get_db)]) -> LibraryStatsResponse:
    return LibraryStatsResponse.model_validate(library_stats(db))


@router.get("/{document_id}", response_model=DocumentResponse)
def document(document_id: int, db: Annotated[Session, Depends(get_db)]) -> DocumentResponse:
    return DocumentResponse.model_validate(get_document_or_404(document_id, db))


@router.post("/{document_id}/process", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def process_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    document = claim_processing(document_id, db, settings)
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    background_tasks.add_task(run_document_processing, document_id, document.processing_run_id, settings, factory)
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/processing-status", response_model=ProcessingStatusResponse)
def processing_status(document_id: int, db: Annotated[Session, Depends(get_db)]) -> ProcessingStatusResponse:
    return ProcessingStatusResponse.model_validate(document_processing_status(document_id, db))


@router.post("/{document_id}/index", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def index_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
) -> DocumentResponse:
    document = claim_indexing(document_id, db, settings)
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    background_tasks.add_task(run_indexing, document_id, document.indexing_run_id, factory, embeddings, vectors)
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/indexing-status", response_model=IndexingStatusResponse)
def document_indexing_status(document_id: int, db: Annotated[Session, Depends(get_db)]) -> IndexingStatusResponse:
    return IndexingStatusResponse.model_validate(indexing_status(document_id, db))


@router.get("/{document_id}/pages", response_model=list[DocumentPageResponse])
def document_pages(document_id: int, db: Annotated[Session, Depends(get_db)]) -> list[DocumentPageResponse]:
    get_document_or_404(document_id, db)
    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.page_number)).all()
    return [DocumentPageResponse.model_validate(page) for page in pages]


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def document_chunks(document_id: int, db: Annotated[Session, Depends(get_db)]) -> list[DocumentChunkResponse]:
    get_document_or_404(document_id, db)
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index)).all()
    return [DocumentChunkResponse.model_validate(chunk) for chunk in chunks]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
) -> None:
    delete_document(get_document_or_404(document_id, db), db, settings, vectors)
