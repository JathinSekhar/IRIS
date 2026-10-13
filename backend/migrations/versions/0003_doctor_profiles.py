"""Doctor role: a profile table for clinicians who can be offered cases (step 1 of the doctor feature)

Revision ID: 0003
Revises: 0002

NOT yet applied to any Supabase project. Same security model as 0001 and 0002: row level security on, no policies, privileges revoked
from `anon` and `authenticated`; only the backend reads or writes. The role itself lives in `profiles.role` (no schema change).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "doctor_profiles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("specialty", sa.String(80), nullable=False),
        sa.Column("registration_number", sa.String(64), nullable=False),
        sa.Column("languages", JSON, nullable=False),
        sa.Column("on_duty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("on_duty_changed_at", sa.DateTime(timezone=True)),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE public.doctor_profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON public.doctor_profiles FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON public.doctor_profiles FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("doctor_profiles")
