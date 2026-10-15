"""Create, process and index the two presentation PDFs when they are missing."""

import logging
from pathlib import Path
from uuid import uuid4

import pymupdf
from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import get_embedding_service
from app.services.indexing import claim_indexing, run_indexing
from app.services.processing import claim_processing, run_document_processing
from app.services.vector_store import get_vector_store


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEMO_DOCUMENTS = {
    "reportmind-demo-project-alpha.pdf": [
        "PROJECT ALPHA REPORT",
        "Executive Overview",
        "Purpose: Build an internal reporting API for operational teams.",
        "Budget: EUR 120,000.",
        "Delivery deadline: 15 October 2026.",
        "Technology: Python and FastAPI.",
        "Primary audience: Internal operations and data teams.",
        "Project identifier: RM-ALPHA-2026.",
    ],
    "reportmind-demo-project-beta.pdf": [
        "PROJECT BETA REPORT",
        "Executive Overview",
        "Purpose: Build a customer-facing reporting portal.",
        "Budget: EUR 95,000.",
        "Delivery deadline: 20 November 2026.",
        "Technology: Node.js and React.",
        "Primary audience: External customers and account managers.",
        "Project identifier: RM-BETA-2026.",
    ],
}


def _pdf_bytes(lines: list[str]) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_textbox(
        pymupdf.Rect(56, 60, 539, 782),
        "\n\n".join(lines),
        fontsize=12,
        lineheight=1.25,
        fontname="helv",
    )
    content = pdf.tobytes()
    pdf.close()
    return content


def _available_document(filename: str, model_name: str, marker: str) -> Document | None:
    with SessionLocal() as db:
        documents = db.scalars(
            select(Document).where(Document.original_filename == filename).order_by(Document.id.desc())
        ).all()
        for document in documents:
            path = Path(document.storage_path)
            has_current_content = db.scalar(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.text.contains(marker),
                ).limit(1)
            ) is not None
            if (
                document.status == "ready"
                and document.indexing_status == "indexed"
                and document.embedding_model == model_name
                and document.indexed_chunk_count > 0
                and path.is_file()
                and has_current_content
            ):
                return document
    return None


def _latest_document(filename: str) -> Document | None:
    with SessionLocal() as db:
        return db.scalar(
            select(Document).where(Document.original_filename == filename).order_by(Document.id.desc()).limit(1)
        )


def _create_document(filename: str, lines: list[str]) -> int:
    settings = get_settings()
    root = settings.document_storage_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}.pdf"
    destination = root / stored_filename
    content = _pdf_bytes(lines)
    destination.write_bytes(content)
    with SessionLocal() as db:
        document = Document(
            original_filename=filename,
            stored_filename=stored_filename,
            file_type="application/pdf",
            file_size=len(content),
            storage_path=str(destination),
            status="uploaded",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document.id


def _refresh_document(document: Document, lines: list[str]) -> int:
    content = _pdf_bytes(lines)
    destination = Path(document.storage_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    with SessionLocal() as db:
        current = db.get(Document, document.id)
        if current is None:
            raise RuntimeError(f"Demo document {document.id} disappeared during refresh")
        current.file_size = len(content)
        db.commit()
    return document.id


def _process_and_index(document_id: int) -> None:
    settings = get_settings()
    embeddings = get_embedding_service()
    vectors = get_vector_store()
    with SessionLocal() as db:
        document = claim_processing(document_id, db, settings)
        processing_run_id = document.processing_run_id
    run_document_processing(document_id, processing_run_id, settings, SessionLocal)
    with SessionLocal() as db:
        document = claim_indexing(document_id, db, settings)
        indexing_run_id = document.indexing_run_id
    run_indexing(document_id, indexing_run_id, SessionLocal, embeddings, vectors)
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.status != "ready" or document.indexing_status != "indexed":
            raise RuntimeError(f"Demo document {document_id} could not be prepared")


def seed_demo_documents() -> None:
    embeddings = get_embedding_service()
    for filename, lines in DEMO_DOCUMENTS.items():
        marker = next(line for line in lines if line.startswith("Project identifier:"))
        existing = _available_document(filename, embeddings.model_name, marker)
        if existing:
            logger.info("Demo document ready: %s (id=%s)", filename, existing.id)
            continue
        latest = _latest_document(filename)
        if latest and latest.status != "processing" and latest.indexing_status != "indexing":
            document_id = _refresh_document(latest, lines)
            logger.info("Refreshing demo document content: %s (id=%s)", filename, document_id)
        else:
            document_id = _create_document(filename, lines)
        _process_and_index(document_id)
        logger.info("Demo document created and indexed: %s (id=%s)", filename, document_id)


if __name__ == "__main__":
    seed_demo_documents()
