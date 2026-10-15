from datetime import datetime

from app.schemas.document import DocumentResponse


def test_mysql_naive_datetime_is_serialized_as_utc():
    response = DocumentResponse(
        id=1,
        original_filename="report.pdf",
        stored_filename="internal.pdf",
        file_type="application/pdf",
        file_size=100,
        storage_path="/data/documents/internal.pdf",
        status="uploaded",
        page_count=None,
        uploaded_at=datetime(2026, 9, 18, 12, 30),
        updated_at=datetime(2026, 9, 18, 12, 30),
    )

    assert response.model_dump(mode="json")["uploaded_at"] == "2026-09-18T12:30:00Z"
