"""Messages, predictions and reviewer actions (the chat and its human review queue)

Revision ID: 0002
Revises: 0001

NOT yet applied to any Supabase project. Apply it with `alembic upgrade head` when you are ready.
Same security model as 0001: row level security on, no policies, privileges revoked from `anon` and `authenticated`; only the backend reads or writes.
Message text is sensitive: consider application-level encryption and a retention period before real use (docs/TRIAGE_INTEGRATION_SPEC.md).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TABLES = ("messages", "predictions", "reviews")


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("helpful", sa.Boolean()),
        sa.CheckConstraint("char_length(text) <= 5000", name="messages_text_length_check"),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("rule_level", sa.String(16), nullable=False),
        sa.Column("rule_hits", JSON, nullable=False),
        sa.Column("baseline_floor", sa.String(16), nullable=False),
        sa.Column("baseline_known", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checkin_id", sa.Integer(), sa.ForeignKey("checkins.id", ondelete="SET NULL")),
        sa.Column("probabilities", JSON),
        sa.Column("model_urgency", sa.String(16)),
        sa.Column("initial_urgency", sa.String(16), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("route", sa.String(24), nullable=False),
        sa.Column("needs_human", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reasons", JSON, nullable=False),
        sa.Column("reply", JSON, nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_human_review"),
        sa.Column("message_urgent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_opened_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("urgency in ('low', 'medium', 'high')", name="predictions_urgency_check"),
        sa.CheckConstraint("status in ('pending_human_review', 'reviewed')", name="predictions_status_check"),
        # A case is never closed without a person: nothing may be 'reviewed' without a review row, enforced in the application and its tests.
    )
    op.create_index("ix_predictions_urgency", "predictions", ["urgency"])
    op.create_index("ix_predictions_status", "predictions", ["status"])
    op.create_index("ix_predictions_message_urgent", "predictions", ["message_urgent"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("from_urgency", sa.String(16)),
        sa.Column("to_urgency", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind in ('escalation', 'judgement')", name="reviews_kind_check"),
    )
    op.create_index("ix_reviews_message_id", "reviews", ["message_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])

    if op.get_bind().dialect.name != "postgresql":
        return
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


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
