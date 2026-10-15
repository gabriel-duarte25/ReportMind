"""Track semantic indexing independently from PDF processing."""

from alembic import op
import sqlalchemy as sa

revision = "20260918_03"
down_revision = "20260918_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("indexing_status", sa.String(20), nullable=False, server_default="not_indexed"))
    op.add_column("documents", sa.Column("indexing_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("indexing_run_id", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("indexed_chunk_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("embedding_model", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("indexing_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("documents", sa.Column("vector_footprint", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint(
        "ck_documents_indexing_status",
        "documents",
        "indexing_status IN ('not_indexed', 'indexing', 'indexed', 'index_failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_indexing_status", "documents", type_="check")
    op.drop_column("documents", "vector_footprint")
    op.drop_column("documents", "indexing_updated_at")
    op.drop_column("documents", "indexed_at")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "indexed_chunk_count")
    op.drop_column("documents", "indexing_run_id")
    op.drop_column("documents", "indexing_error")
    op.drop_column("documents", "indexing_status")
