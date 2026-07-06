"""Verify demo user and legacy ownership backfill.

Revision ID: 20260514_03
Revises: 20260514_02
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260514_03"
down_revision = "20260514_02"
branch_labels = None
depends_on = None


def _table_exists(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    connection = op.get_bind()
    demo_user = connection.execute(
        sa.text("SELECT id FROM users WHERE username = :username AND is_active = :is_active"),
        {"username": "test-01", "is_active": True},
    ).first()
    if not demo_user:
        raise RuntimeError("expected active demo user test-01 after auth migration")

    conversation_nulls = 0
    material_nulls = 0
    if _table_exists(connection, "tutor_conversations"):
        conversation_nulls = connection.execute(
            sa.text("SELECT COUNT(*) FROM tutor_conversations WHERE user_id IS NULL")
        ).scalar()
    if _table_exists(connection, "study_materials"):
        material_nulls = connection.execute(
            sa.text("SELECT COUNT(*) FROM study_materials WHERE user_id IS NULL")
        ).scalar()
    if conversation_nulls or material_nulls:
        raise RuntimeError("legacy ownership verification failed; NULL user_id rows remain")


def downgrade() -> None:
    # Verification-only migration. The data and schema changes are owned by
    # revision 20260514_02 so downgrade work stays there.
    pass
