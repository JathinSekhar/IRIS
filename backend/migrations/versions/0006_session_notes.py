"""Session notes: the documented form a doctor completes to end a conversation (step 4 of the doctor feature)

Revision ID: 0006
Revises: 0005

NOT yet applied to any Supabase project. Same security model as 0001-0005: row level security on, privileges revoked from `anon` and
`authenticated`; only the backend reads or writes. A clinical record: consider encryption and a retention period before real use.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_notes",
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("consult_cases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("doctor_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("concerns", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(8), nullable=False),
        sa.Column("actions_taken", sa.Text(), nullable=False),
        sa.Column("follow_up", sa.Text(), nullable=False),
        sa.Column("referral", sa.Text()),
        sa.Column("emergency_services_contacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mode in ('chat', 'video', 'both')", name="session_notes_mode_check"),
        sa.CheckConstraint("risk_level in ('low', 'medium', 'high')", name="session_notes_risk_check"),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE public.session_notes ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON public.session_notes FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON public.session_notes FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("session_notes")
