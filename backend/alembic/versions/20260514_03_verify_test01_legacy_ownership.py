"""Verify demo user and legacy ownership backfill.

Revision ID: 20260514_03
Revises: 20260514_02
Create Date: 2026-05-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_03"
down_revision = "20260514_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    demo_user = connection.execute(
        sa.text("SELECT id FROM users WHERE username = :username AND is_active = 1"),
        {"username": "test-01"},
    ).first()
    if not demo_user:
        raise RuntimeError("expected active demo user test-01 after auth migration")

    conversation_nulls = connection.execute(
        sa.text("SELECT COUNT(*) FROM tutor_conversations WHERE user_id IS NULL")
    ).scalar()
    material_nulls = connection.execute(
        sa.text("SELECT COUNT(*) FROM study_materials WHERE user_id IS NULL")
    ).scalar()
    if conversation_nulls or material_nulls:
        raise RuntimeError("legacy ownership verification failed; NULL user_id rows remain")


def downgrade() -> None:
    # Verification-only migration. The data and schema changes are owned by
    # revision 20260514_02 so downgrade work stays there.
    pass
