from io import BytesIO

import pytest
import pymupdf
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import Document  # noqa: F401 - registers model metadata
from app.services.documents import safe_display_filename


def pdf_bytes() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_start = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode())
    return bytes(content)


@pytest.fixture
def client(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", document_storage_path=tmp_path, max_upload_size_mb=1)

    def test_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client, tmp_path
    app.dependency_overrides.clear()
    engine.dispose()


def upload(client: TestClient, filename="report.pdf", content=None, mime="application/pdf"):
    if content is None:
        content = pdf_bytes()
    return client.post("/api/v1/documents/upload", files={"file": (filename, BytesIO(content), mime)})


def text_pdf(*pages: str) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((60, 72), text, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def test_upload_valid_pdf(client):
    api, storage = client
    response = upload(api)
    assert response.status_code == 201
    document = response.json()
    assert document["original_filename"] == "report.pdf"
    assert document["stored_filename"] != "report.pdf"
    assert document["stored_filename"].endswith(".pdf")
    assert document["file_size"] == len(pdf_bytes())
    assert document["status"] == "uploaded"
    assert document["page_count"] is None
    assert (storage / document["stored_filename"]).read_bytes() == pdf_bytes()


def test_rejects_invalid_extension(client):
    api, _ = client
    assert upload(api, filename="report.txt").status_code == 400
    assert api.get("/api/v1/documents").json() == []


def test_rejects_invalid_mime_and_signature(client):
    api, _ = client
    assert upload(api, mime="text/plain").status_code == 400
    assert upload(api, content=b"not a pdf").status_code == 400


def test_rejects_empty_upload(client):
    api, storage = client
    assert upload(api, content=b"").status_code == 400
    assert list(storage.iterdir()) == []


def test_rejects_file_above_limit(client):
    api, storage = client
    response = upload(api, content=b"%PDF-1.4\n" + b"x" * (1024 * 1024))
    assert response.status_code == 413
    assert list(storage.iterdir()) == []


def test_list_and_get_document(client):
    api, _ = client
    first = upload(api, filename="first.pdf").json()
    second = upload(api, filename="second.pdf").json()
    listing = api.get("/api/v1/documents")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [second["id"], first["id"]]
    detail = api.get(f"/api/v1/documents/{first['id']}")
    assert detail.status_code == 200
    assert detail.json() == first


def test_missing_document(client):
    api, _ = client
    assert api.get("/api/v1/documents/999").status_code == 404
    assert api.delete("/api/v1/documents/999").status_code == 404


def test_delete_document_and_file(client):
    api, storage = client
    document = upload(api).json()
    path = storage / document["stored_filename"]
    assert path.exists()
    assert api.delete(f"/api/v1/documents/{document['id']}").status_code == 204
    assert not path.exists()
    assert api.get("/api/v1/documents").json() == []


@pytest.mark.parametrize("filename", ["../escape.pdf", "..\\escape.pdf", "folder/report.pdf"])
def test_rejects_dangerous_filenames(client, filename):
    api, storage = client
    response = upload(api, filename=filename)
    assert response.status_code in {400, 422}
    assert list(storage.iterdir()) == []


def test_rejects_control_characters_before_multipart_parsing():
    with pytest.raises(HTTPException):
        safe_display_filename("\x00report.pdf")


def test_storage_filename_is_independent_of_display_name(client):
    api, storage = client
    document = upload(api, filename="quarterly report (final).PDF").json()
    assert document["original_filename"] == "quarterly report (final).PDF"
    assert document["stored_filename"] != document["original_filename"]
    assert (storage / document["stored_filename"]).exists()


def test_process_pdf_pages_sections_chunks_and_stats(client):
    api, _ = client
    document = upload(api, content=text_pdf("Introduction\nThis is the introduction to the report.", "Results\nThe results are recorded here.")).json()
    response = api.post(f"/api/v1/documents/{document['id']}/process")
    assert response.status_code == 202
    assert response.json()["status"] == "processing"

    base = f"/api/v1/documents/{document['id']}"
    status = api.get(f"{base}/processing-status").json()
    pages = api.get(f"{base}/pages").json()
    chunks = api.get(f"{base}/chunks").json()
    assert status["status"] == "ready"
    assert status["page_count"] == 2
    assert status["sections_detected"] == 2
    assert status["chunk_count"] == 2
    assert status["word_count"] > 0
    assert [page["page_number"] for page in pages] == [1, 2]
    assert "introduction" in pages[0]["cleaned_text"].lower()
    assert [chunk["section"] for chunk in chunks] == ["Introduction", "Results"]
    assert [chunk["page_start"] for chunk in chunks] == [1, 2]
    assert [chunk["page_id"] for chunk in chunks] == [page["id"] for page in pages]
    assert all(chunk["document_id"] == document["id"] for chunk in chunks)
    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1]
    assert api.get("/api/v1/documents/stats").json() == {"document_count": 1, "page_count": 2, "chunk_count": 2}

    assert api.post(f"{base}/process").status_code == 202
    assert len(api.get(f"{base}/pages").json()) == 2
    assert len(api.get(f"{base}/chunks").json()) == 2
    assert api.delete(base).status_code == 204
    assert api.get("/api/v1/documents/stats").json() == {"document_count": 0, "page_count": 0, "chunk_count": 0}


def test_chunk_can_span_pages(client):
    api, _ = client
    document = upload(api, content=text_pdf("A short first page of text.", "A short second page of text.")).json()
    api.post(f"/api/v1/documents/{document['id']}/process")
    chunks = api.get(f"/api/v1/documents/{document['id']}/chunks").json()
    assert len(chunks) == 1
    assert (chunks[0]["page_start"], chunks[0]["page_end"]) == (1, 2)


def test_blank_pages_produce_no_chunks(client):
    api, _ = client
    document = upload(api, content=text_pdf("", "")).json()
    api.post(f"/api/v1/documents/{document['id']}/process")
    status = api.get(f"/api/v1/documents/{document['id']}/processing-status").json()
    assert status["status"] == "ready"
    assert status["page_count"] == 2
    assert status["word_count"] == 0
    assert api.get(f"/api/v1/documents/{document['id']}/chunks").json() == []


def test_graphics_only_pdf_has_no_selectable_text(client):
    api, _ = client
    graphic = pymupdf.open()
    graphic.new_page().draw_rect(pymupdf.Rect(50, 50, 300, 300), color=(0, 0, 1), fill=(0.2, 0.4, 0.8))
    content = graphic.tobytes()
    graphic.close()
    document = upload(api, content=content).json()
    assert api.post(f"/api/v1/documents/{document['id']}/process").status_code == 202
    result = api.get(f"/api/v1/documents/{document['id']}/processing-status").json()
    assert (result["status"], result["page_count"], result["chunk_count"]) == ("ready", 1, 0)


def test_corrupt_pdf_marks_failed_and_does_not_crash_api(client):
    api, _ = client
    document = upload(api, content=b"%PDF-invalid-payload").json()
    assert api.post(f"/api/v1/documents/{document['id']}/process").status_code == 202
    status = api.get(f"/api/v1/documents/{document['id']}/processing-status").json()
    assert status["status"] == "failed"
    assert status["processing_error"]
    assert api.get("/health").status_code == 200


def test_failed_reprocessing_keeps_previous_results(client):
    api, storage = client
    document = upload(api, content=text_pdf("A page with stable text.")).json()
    base = f"/api/v1/documents/{document['id']}"
    assert api.post(f"{base}/process").status_code == 202
    original = api.get(f"{base}/pages").json()
    (storage / document["stored_filename"]).write_bytes(b"%PDF-invalid-payload")
    assert api.post(f"{base}/process").status_code == 202
    assert api.get(f"{base}/processing-status").json()["status"] == "failed"
    assert api.get(f"{base}/pages").json() == original


def test_processing_missing_document(client):
    api, _ = client
    for endpoint in ["/process", "/processing-status", "/pages", "/chunks"]:
        response = api.post(f"/api/v1/documents/999{endpoint}") if endpoint == "/process" else api.get(f"/api/v1/documents/999{endpoint}")
        assert response.status_code == 404


def test_many_pages_are_processed(client):
    api, _ = client
    document = upload(api, content=text_pdf(*[f"Page {number} contains selectable text." for number in range(1, 31)])).json()
    assert api.post(f"/api/v1/documents/{document['id']}/process").status_code == 202
    assert api.get(f"/api/v1/documents/{document['id']}/processing-status").json()["page_count"] == 30
