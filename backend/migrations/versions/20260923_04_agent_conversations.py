"""Persist document agent conversations."""

from alembic import op
import sqlalchemy as sa

revision = "20260923_04"
down_revision = "20260918_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_conversation_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_conversation_messages_conversation_id",
        "agent_conversation_messages",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_conversation_messages_conversation_id", table_name="agent_conversation_messages")
    op.drop_table("agent_conversation_messages")
    op.drop_table("agent_conversations")
