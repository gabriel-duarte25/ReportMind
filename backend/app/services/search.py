"""Vector retrieval, reconciled against current MySQL chunks."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore, VectorStoreError


def semantic_search(
    query: str,
    limit: int,
    requested_document_ids: list[int] | None,
    db: Session,
    embeddings: EmbeddingService,
    vectors: VectorStore,
) -> list[dict]:
    eligible = select(Document.id).where(
        Document.status == "ready",
        Document.indexing_status == "indexed",
        Document.embedding_model == embeddings.model_name,
    )
    if requested_document_ids is not None:
        if not requested_document_ids:
            return []
        eligible = eligible.where(Document.id.in_(requested_document_ids))
    document_ids = list(db.scalars(eligible))
    if not document_ids:
        return []

    try:
        query_vector = embeddings.embed_query(query)
        points = vectors.search(query_vector, document_ids, max(limit * 3, 20))
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail="Vector database unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Embedding model unavailable") from exc

    chunk_ids = [point.payload.get("chunk_id") for point in points if point.payload]
    if not chunk_ids:
        return []
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id.in_(chunk_ids), Document.id.in_(document_ids))
    ).all()
    by_id = {chunk.id: (chunk, document) for chunk, document in rows}
    results: list[dict] = []
    for point in points:
        chunk_id = point.payload.get("chunk_id") if point.payload else None
        match = by_id.get(chunk_id)
        if match is None:
            continue
        chunk, document = match
        if document.indexing_status != "indexed":
            continue
        results.append({
            "score": point.score,
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_name": document.original_filename,
            "text": chunk.text,
            "section": chunk.section,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        })
        if len(results) >= limit:
            break
    return results
