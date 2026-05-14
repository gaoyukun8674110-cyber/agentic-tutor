"""Seed demo user and tighten user-scoped tables.

Revision ID: 20260514_02
Revises: 20260514_01
Create Date: 2026-05-14
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from argon2 import PasswordHasher


revision = "20260514_02"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_test_user(connection) -> None:
    existing = connection.execute(sa.text("SELECT id FROM users WHERE username = :username"), {"username": "test-01"}).first()
    if existing:
        return

    now = _now()
    password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash("123456")
    connection.execute(
        sa.text(
            """
            INSERT INTO users (username, email, password_hash, is_active, created_at, updated_at, last_login_at)
            VALUES (:username, NULL, :password_hash, 1, :created_at, :updated_at, NULL)
            """
        ),
        {
            "username": "test-01",
            "password_hash": password_hash,
            "created_at": now,
            "updated_at": now,
        },
    )


def _backfill_legacy_rows(connection) -> None:
    connection.execute(sa.text("UPDATE tutor_conversations SET user_id = 'test-01' WHERE user_id IS NULL"))
    connection.execute(sa.text("UPDATE study_materials SET user_id = 'test-01' WHERE user_id IS NULL"))
    conversation_nulls = connection.execute(sa.text("SELECT COUNT(*) FROM tutor_conversations WHERE user_id IS NULL")).scalar()
    material_nulls = connection.execute(sa.text("SELECT COUNT(*) FROM study_materials WHERE user_id IS NULL")).scalar()
    if conversation_nulls or material_nulls:
        raise RuntimeError("legacy user_id backfill failed; NULL user_id rows remain")


def upgrade() -> None:
    connection = op.get_bind()
    _seed_test_user(connection)
    _backfill_legacy_rows(connection)

    with op.batch_alter_table("tutor_conversations") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_foreign_key(
            "fk_tutor_conversations_user_id_users",
            "users",
            ["user_id"],
            ["username"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("study_materials") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_foreign_key(
            "fk_study_materials_user_id_users",
            "users",
            ["user_id"],
            ["username"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("study_materials") as batch_op:
        batch_op.drop_constraint("fk_study_materials_user_id_users", type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=True)

    with op.batch_alter_table("tutor_conversations") as batch_op:
        batch_op.drop_constraint("fk_tutor_conversations_user_id_users", type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=True)

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE tutor_conversations SET user_id = NULL WHERE user_id = 'test-01'"))
    connection.execute(sa.text("UPDATE study_materials SET user_id = NULL WHERE user_id = 'test-01'"))
    connection.execute(sa.text("DELETE FROM users WHERE username = 'test-01'"))
