from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    stored_filename: str
    file_type: str
    file_size: int
    storage_path: str
    status: Literal["uploaded", "processing", "ready", "failed"]
    page_count: int | None
    processing_error: str | None = None
    indexing_status: Literal["not_indexed", "indexing", "indexed", "index_failed"] = "not_indexed"
    indexing_error: str | None = None
    indexed_chunk_count: int = 0
    embedding_model: str | None = None
    indexed_at: datetime | None = None
    uploaded_at: datetime
    updated_at: datetime

    @field_serializer("uploaded_at", "updated_at", "indexed_at")
    def serialize_utc_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class DocumentPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    page_number: int
    raw_text: str
    cleaned_text: str
    character_count: int
    word_count: int


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    page_id: int
    text: str
    page_start: int
    page_end: int
    section: str | None
    chunk_index: int
    character_count: int
    word_count: int
    created_at: datetime

    @field_serializer("created_at")
    def serialize_utc_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ProcessingStatusResponse(BaseModel):
    document_id: int
    status: Literal["uploaded", "processing", "ready", "failed"]
    page_count: int
    word_count: int
    chunk_count: int
    sections_detected: int
    processing_error: str | None
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_utc_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LibraryStatsResponse(BaseModel):
    document_count: int
    page_count: int
    chunk_count: int


class IndexingStatusResponse(BaseModel):
    document_id: int
    indexing_status: Literal["not_indexed", "indexing", "indexed", "index_failed"]
    chunk_count: int
    indexed_vector_count: int
    embedding_model: str | None
    indexing_error: str | None
    indexed_at: datetime | None

    @field_serializer("indexed_at")
    def serialize_utc_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
