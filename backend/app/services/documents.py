import logging
import os
import unicodedata
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage
from app.services.processing import stored_pdf_path
from app.services.vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


def safe_display_filename(filename: str | None) -> str:
    name = unicodedata.normalize("NFC", filename or "").strip()
    if not name or len(name) > 255 or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if "/" in name or "\\" in name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(name).suffix.lower() != ".pdf" or not Path(name).stem.strip(". "):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    return name


async def save_document(upload: UploadFile, db: Session, settings: Settings) -> Document:
    filename = safe_display_filename(upload.filename)
    if upload.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File MIME type must be application/pdf")

    root = settings.document_storage_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}.pdf"
    destination = root / stored_filename
    temporary = root / f".{stored_filename}.part"
    total = 0

    try:
        with temporary.open("xb") as output:
            while chunk := await upload.read(CHUNK_SIZE):
                if total == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(status_code=400, detail="File content is not a PDF")
                total += len(chunk)
                if total > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=413, detail="PDF exceeds the upload size limit")
                output.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="Empty files are not allowed")

        os.replace(temporary, destination)
        document = Document(
            original_filename=filename,
            stored_filename=stored_filename,
            file_type="application/pdf",
            file_size=total,
            storage_path=str(destination),
            status="uploaded",
            page_count=None,
        )
        db.add(document)
        db.flush()
        db.refresh(document)
        db.commit()
        return document
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def list_documents(db: Session) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.uploaded_at.desc(), Document.id.desc())).all())


def get_document_or_404(document_id: int, db: Session) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def delete_document(document: Document, db: Session, settings: Settings, vectors: VectorStore | None = None) -> None:
    document = db.scalar(select(Document).where(Document.id == document.id).with_for_update())
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status == "processing" or document.indexing_status == "indexing":
        raise HTTPException(status_code=409, detail="Wait until processing or indexing finishes before deleting")
    root = settings.document_storage_path.resolve()
    try:
        stored_path = stored_pdf_path(document, settings)
    except ValueError:
        logger.error("Invalid storage path for document %s", document.id)
        raise HTTPException(status_code=500, detail="Document storage path is invalid")

    tombstone = root / f".{document.stored_filename}.{uuid4().hex}.deleting"
    renamed = False
    try:
        if document.vector_footprint:
            if vectors is None:
                raise HTTPException(status_code=503, detail="Vector database unavailable")
            try:
                vectors.delete_document(document.id)
            except VectorStoreError as exc:
                raise HTTPException(status_code=503, detail="Vector database unavailable") from exc
        if stored_path.exists():
            os.replace(stored_path, tombstone)
            renamed = True
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        if renamed:
            os.replace(tombstone, stored_path)
        raise

    if renamed:
        tombstone.unlink()
