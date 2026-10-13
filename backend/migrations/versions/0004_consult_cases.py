"""Doctor requests: consult cases and per-doctor declines (step 2 of the doctor feature)

Revision ID: 0004
Revises: 0003

NOT yet applied to any Supabase project. Same security model as 0001-0003: row level security on, privileges revoked from `anon` and
`authenticated`; only the backend reads or writes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ("consult_cases", "consult_declines")


def upgrade() -> None:
    op.create_table(
        "consult_cases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="open"),
        sa.Column("source", sa.String(16), nullable=False, server_default="user"),
        sa.Column("share_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("accepted_by", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="SET NULL")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("video_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ai_summary_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("ai_summary_at", sa.DateTime(timezone=True)),
        sa.Column("ai_summary_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_summary_tried_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state in ('open', 'accepted', 'in_session', 'closed', 'cancelled')", name="consult_cases_state_check"),
        sa.CheckConstraint("source in ('user', 'system', 'reviewer')", name="consult_cases_source_check"),
    )
    op.create_index("ix_consult_cases_user_id", "consult_cases", ["user_id"])
    op.create_index("ix_consult_cases_state", "consult_cases", ["state"])
    op.create_index("ix_consult_cases_accepted_by", "consult_cases", ["accepted_by"])
    op.create_index("ix_consult_cases_created_at", "consult_cases", ["created_at"])
    op.create_table(
        "consult_declines",
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("consult_cases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("doctor_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON public.consult_cases, public.consult_declines FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON public.consult_cases, public.consult_declines FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
