from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_pages_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="pages")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="page", passive_deletes=True)
