"""Add page-level extraction and contextual chunks."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "20260918_02"
down_revision = "20260918_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processing_run_id", sa.String(32), nullable=True))
    op.create_table(
        "document_pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("cleaned_text", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_number"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(128), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_page_id", "document_chunks", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_page_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_column("documents", "processing_run_id")
    op.drop_column("documents", "processing_error")
