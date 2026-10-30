"""Persist human edits and review transitions for product drafts."""

from alembic import op
import sqlalchemy as sa


revision = "0002_product_draft_audit"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_audit_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("draft_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "action IN ('edited', 'approved', 'excluded')",
            name="ck_draft_audit_action",
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["product_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_draft_audit_events_draft_created",
        "draft_audit_events",
        ["draft_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_draft_audit_events_draft_created", table_name="draft_audit_events")
    op.drop_table("draft_audit_events")
