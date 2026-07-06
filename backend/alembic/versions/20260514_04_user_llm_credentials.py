"""Add per-user LLM credentials.

Revision ID: 20260514_04
Revises: 20260514_03
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260514_04"
down_revision = "20260514_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_llm_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(length=50), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("api_key_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_validated_at", sa.String(length=50), nullable=True),
        sa.Column("last_validation_error_code", sa.String(length=32), nullable=True),
        sa.Column("last_used_at", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.String(length=50), nullable=False),
        sa.UniqueConstraint("user_id", "provider_id", name="uq_user_llm_credentials_user_provider"),
    )
    op.create_index("idx_user_llm_credentials_user", "user_llm_credentials", ["user_id"])
    op.create_index(
        "idx_user_llm_credentials_fingerprint",
        "user_llm_credentials",
        ["api_key_fingerprint"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_user_llm_credentials_default "
            "ON user_llm_credentials(user_id) WHERE is_default = TRUE"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_user_llm_credentials_default")
    op.drop_index("idx_user_llm_credentials_fingerprint", table_name="user_llm_credentials")
    op.drop_index("idx_user_llm_credentials_user", table_name="user_llm_credentials")
    op.drop_table("user_llm_credentials")
