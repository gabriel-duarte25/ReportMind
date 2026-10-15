"""Manual PDF processing and transactional replacement of derived data."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.document_processing.chunking import chunk_segments
from app.document_processing.cleaning import clean_text
from app.document_processing.pdf import iter_pdf_pages
from app.document_processing.sections import SectionSegment, split_page_sections
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage

logger = logging.getLogger(__name__)


def stored_pdf_path(document: Document, settings: Settings) -> Path:
    root = settings.document_storage_path.resolve()
    expected = root / document.stored_filename
    if expected.suffix.lower() != ".pdf" or expected.name != document.stored_filename or Path(document.storage_path).resolve() != expected:
        raise ValueError("Invalid document storage path")
    return expected


def claim_processing(document_id: int, db: Session, settings: Settings) -> Document:
    run_id = uuid4().hex
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=settings.processing_stale_minutes)
    stale_index_before = now - timedelta(minutes=settings.indexing_stale_minutes)
    changed = db.execute(
        update(Document)
        .where(Document.id == document_id)
        .where(or_(Document.status != "processing", Document.updated_at < stale_before))
        .where(or_(Document.indexing_status != "indexing", Document.indexing_updated_at < stale_index_before))
        .values(
            status="processing", processing_error=None, processing_run_id=run_id, updated_at=now,
            indexing_status="not_indexed", indexing_error=None, indexing_run_id=None,
            indexed_chunk_count=0, embedding_model=None, indexed_at=None, indexing_updated_at=now,
        )
    )
    if changed.rowcount == 0:
        exists = db.scalar(select(Document.id).where(Document.id == document_id))
        db.rollback()
        if exists is None:
            raise HTTPException(status_code=404, detail="Document not found")
        raise HTTPException(status_code=409, detail="Document is already processing or indexing")
    db.commit()
    return db.get(Document, document_id)


def run_document_processing(document_id: int, run_id: str, settings: Settings, factory: sessionmaker[Session]) -> None:
    try:
        with factory() as db:
            document = db.get(Document, document_id)
            if document is None or document.processing_run_id != run_id:
                return
            path = stored_pdf_path(document, settings)

        if not path.is_file():
            raise FileNotFoundError("Stored PDF is unavailable")

        pages: list[tuple[int, str, str]] = []
        segments: list[SectionSegment] = []
        section: str | None = None
        for number, raw in iter_pdf_pages(path):
            cleaned = clean_text(raw)
            pages.append((number, raw, cleaned))
            page_segments, section = split_page_sections(raw, number, section)
            segments.extend(page_segments)
        drafts = chunk_segments(segments, settings.chunk_size_chars, settings.chunk_overlap_chars)

        with factory() as db:
            with db.begin():
                document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
                if document is None or document.processing_run_id != run_id:
                    return
                db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
                db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
                page_ids: dict[int, int] = {}
                for number, raw, cleaned in pages:
                    page = DocumentPage(
                        document_id=document_id,
                        page_number=number,
                        raw_text=raw,
                        cleaned_text=cleaned,
                        character_count=len(cleaned),
                        word_count=len(cleaned.split()),
                    )
                    db.add(page)
                    db.flush()
                    page_ids[number] = page.id
                for draft in drafts:
                    db.add(DocumentChunk(
                        document_id=document_id,
                        page_id=page_ids[draft.page_start],
                        text=draft.text,
                        page_start=draft.page_start,
                        page_end=draft.page_end,
                        section=draft.section,
                        chunk_index=draft.chunk_index,
                        character_count=draft.character_count,
                        word_count=draft.word_count,
                    ))
                document.page_count = len(pages)
                document.status = "ready"
                document.processing_error = None
                document.processing_run_id = None
                document.updated_at = datetime.now(timezone.utc)
        logger.info("Processed document %s: %s pages, %s chunks", document_id, len(pages), len(drafts))
    except Exception:
        logger.exception("Failed to process document %s", document_id)
        with factory() as db:
            db.execute(
                update(Document)
                .where(Document.id == document_id, Document.processing_run_id == run_id)
                .values(
                    status="failed",
                    processing_error="Unable to process PDF. Check that it is valid and not encrypted.",
                    processing_run_id=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            db.commit()


def document_processing_status(document_id: int, db: Session) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    page_count, word_count = db.execute(
        select(func.count(DocumentPage.id), func.coalesce(func.sum(DocumentPage.word_count), 0))
        .where(DocumentPage.document_id == document_id)
    ).one()
    chunk_count, sections_detected = db.execute(
        select(func.count(DocumentChunk.id), func.count(func.distinct(DocumentChunk.section)))
        .where(DocumentChunk.document_id == document_id)
    ).one()
    return {
        "document_id": document_id,
        "status": document.status,
        "page_count": page_count,
        "word_count": word_count,
        "chunk_count": chunk_count,
        "sections_detected": sections_detected,
        "processing_error": document.processing_error,
        "updated_at": document.updated_at,
    }


def library_stats(db: Session) -> dict[str, int]:
    return {
        "document_count": db.scalar(select(func.count(Document.id))) or 0,
        "page_count": db.scalar(select(func.count(DocumentPage.id))) or 0,
        "chunk_count": db.scalar(select(func.count(DocumentChunk.id))) or 0,
    }
