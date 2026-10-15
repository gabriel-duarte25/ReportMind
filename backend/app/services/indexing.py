"""Manual vector indexing with an independent document state machine."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


def claim_indexing(document_id: int, db: Session, settings: Settings) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != "ready":
        raise HTTPException(status_code=409, detail="Process the PDF before indexing")
    chunk_count = db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)) or 0
    if chunk_count == 0:
        raise HTTPException(status_code=409, detail="Document has no text chunks to index")
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=settings.indexing_stale_minutes)
    updated_at = document.indexing_updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if document.indexing_status == "indexing" and updated_at >= stale_before:
        raise HTTPException(status_code=409, detail="Document is already indexing")
    document.indexing_status = "indexing"
    document.indexing_error = None
    document.indexing_run_id = uuid4().hex
    document.indexed_chunk_count = 0
    document.embedding_model = None
    document.indexed_at = None
    document.indexing_updated_at = now
    db.commit()
    return document


def run_indexing(
    document_id: int,
    run_id: str,
    factory: sessionmaker[Session],
    embeddings: EmbeddingService,
    vectors: VectorStore,
) -> None:
    try:
        with factory() as db:
            document = db.get(Document, document_id)
            if document is None or document.indexing_run_id != run_id or document.status != "ready":
                return
            chunks = list(db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index)
            ))
            if not chunks:
                raise ValueError("Document has no text chunks")

        chunk_vectors = embeddings.embed_passages([chunk.text for chunk in chunks])

        with factory() as db:
            changed = db.execute(
                update(Document)
                .where(Document.id == document_id, Document.indexing_run_id == run_id, Document.status == "ready")
                .values(vector_footprint=True)
            )
            db.commit()
            if changed.rowcount == 0:
                return

        count = vectors.replace_document(document, chunks, chunk_vectors)
        if count != len(chunks):
            raise VectorStoreError("Qdrant vector count does not match chunk count")
        with factory() as db:
            changed = db.execute(
                update(Document)
                .where(Document.id == document_id, Document.indexing_run_id == run_id, Document.status == "ready")
                .values(
                    indexing_status="indexed", indexing_error=None, indexing_run_id=None,
                    indexed_chunk_count=count, embedding_model=embeddings.model_name,
                    indexed_at=datetime.now(timezone.utc), indexing_updated_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
            if changed.rowcount:
                logger.info("Indexed document %s: %s vectors", document_id, count)
    except Exception as exc:
        logger.exception("Failed to index document %s", document_id)
        message = "Vector database unavailable or indexing failed." if isinstance(exc, VectorStoreError) else "Could not generate embeddings for this document."
        with factory() as db:
            db.execute(
                update(Document)
                .where(Document.id == document_id, Document.indexing_run_id == run_id)
                .values(
                    indexing_status="index_failed", indexing_error=message, indexing_run_id=None,
                    indexed_chunk_count=0, embedding_model=None, indexed_at=None,
                    indexing_updated_at=datetime.now(timezone.utc),
                )
            )
            db.commit()


def indexing_status(document_id: int, db: Session) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": document_id,
        "indexing_status": document.indexing_status,
        "chunk_count": db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)) or 0,
        "indexed_vector_count": document.indexed_chunk_count,
        "embedding_model": document.embedding_model,
        "indexing_error": document.indexing_error,
        "indexed_at": document.indexed_at,
    }
