from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="ck_documents_status"),
        CheckConstraint("indexing_status IN ('not_indexed', 'indexing', 'indexed', 'index_failed')", name="ck_documents_indexing_status"),
        UniqueConstraint("stored_filename", name="uq_documents_stored_filename"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(64), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    indexing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_indexed")
    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexing_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    indexed_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    vector_footprint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pages: Mapped[list["DocumentPage"]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
