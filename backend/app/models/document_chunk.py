from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    document: Mapped["Document"] = relationship(back_populates="chunks")
    page: Mapped["DocumentPage"] = relationship(back_populates="chunks")
