"""Initial schema: profiles, consents, check-ins, audit log

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TABLES = ("profiles", "consents", "checkins", "audit_log")


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(32)),
        sa.Column("occupation", sa.String(32)),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("phone", sa.String(32)),
        sa.Column("emergency_contact", sa.String(200)),
        sa.Column("guardian_name", sa.String(120)),
        sa.Column("guardian_email", sa.String(254)),
        sa.Column("guardian_consent_status", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role in ('user', 'reviewer')", name="profiles_role_check"),
    )
    op.create_index("ix_profiles_email", "profiles", ["email"])

    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_consents_user_id", "consents", ["user_id"])

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("questionnaire_version", sa.String(16), nullable=False),
        sa.Column("answers", JSON, nullable=False),
        sa.Column("scores", JSON, nullable=False),
        sa.Column("baseline_risk", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("safety_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("free_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_checkins_user_id", "checkins", ["user_id"])
    op.create_index("ix_checkins_safety_flag", "checkins", ["safety_flag"])
    op.create_index("ix_checkins_escalated", "checkins", ["escalated"])
    op.create_index("ix_checkins_created_at", "checkins", ["created_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(40)),
        sa.Column("target_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    if op.get_bind().dialect.name != "postgresql":
        return

    # Supabase specifics ---------------------------------------------------------------------------------------
    # Profiles share their id with Supabase Auth users; deleting the auth user deletes the profile and, by cascade,
    # that person's consents and check-ins.
    op.execute(
        """
        DO $$ BEGIN
          IF to_regclass('auth.users') IS NOT NULL THEN
            ALTER TABLE public.profiles
              ADD CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE;
          END IF;
        END $$;
        """
    )

    # Supabase exposes every table in `public` through a public REST API. Deny it everything:
    #   * row level security on with NO policies  -> anon/authenticated see no rows
    #   * privileges revoked                      -> they cannot even attempt a query
    # The backend connects as `postgres`, which bypasses RLS, so it is unaffected. All data access goes through the
    # FastAPI backend; the browser never talks to these tables directly.
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
            REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
            REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
          END IF;
        END $$;
        """
    )
    # Future tables should not be exposed by default either.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
