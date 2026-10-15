"""Create documents table."""

from alembic import op
import sqlalchemy as sa

revision = "20260918_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="ck_documents_status"),
        sa.UniqueConstraint("stored_filename", name="uq_documents_stored_filename"),
    )
    op.create_index("ix_documents_uploaded_at", "documents", ["uploaded_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_uploaded_at", table_name="documents")
    op.drop_table("documents")
