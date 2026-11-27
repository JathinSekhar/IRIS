"""Chats: each message can belong to a conversation ("New chat" starts another; "Past chats" lists them)

Revision ID: 0007
Revises: 0006

NOT yet applied to any Supabase project (like 0002-0006). The column is nullable: messages written before chats existed stay in one
"earlier" chat. The messages table keeps its row level security and revoked privileges from 0002.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("conversation_id", sa.String(36), nullable=True))
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_column("messages", "conversation_id")
