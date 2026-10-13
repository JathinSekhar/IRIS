"""Doctor conversation: messages between a person and the doctor who accepted their case (step 3 of the doctor feature)

Revision ID: 0005
Revises: 0004

NOT yet applied to any Supabase project. Same security model as 0001-0004: row level security on, privileges revoked from `anon` and
`authenticated`; only the backend reads or writes. Message text is sensitive: consider application-level encryption and a retention period before
real use.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consult_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("consult_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_role", sa.String(8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sender_role in ('user', 'doctor')", name="consult_messages_role_check"),
        sa.CheckConstraint("char_length(text) <= 2000", name="consult_messages_text_length_check"),
    )
    op.create_index("ix_consult_messages_case_id", "consult_messages", ["case_id"])
    op.create_index("ix_consult_messages_created_at", "consult_messages", ["created_at"])
    op.create_table(
        "consult_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("consult_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_role", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind in ('request','accept','decline','end','offer','answer','ice')", name="consult_signals_kind_check"),
    )
    op.create_index("ix_consult_signals_case_id", "consult_signals", ["case_id"])
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE public.consult_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.consult_signals ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON public.consult_messages, public.consult_signals FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON public.consult_messages, public.consult_signals FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("consult_signals")
    op.drop_table("consult_messages")
