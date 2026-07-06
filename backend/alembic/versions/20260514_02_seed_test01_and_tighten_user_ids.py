"""Seed demo user and tighten user-scoped tables.

Revision ID: 20260514_02
Revises: 20260514_01
Create Date: 2026-05-14
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from argon2 import PasswordHasher

from alembic import op

revision = "20260514_02"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _seed_test_user(connection) -> None:
    existing = connection.execute(
        sa.text("SELECT id FROM users WHERE username = :username"), {"username": "test-01"}
    ).first()
    if existing:
        return

    now = _now()
    password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash("123456")
    connection.execute(
        sa.text(
            """
            INSERT INTO users (username, email, password_hash, is_active, created_at, updated_at, last_login_at)
            VALUES (:username, NULL, :password_hash, :is_active, :created_at, :updated_at, NULL)
            """
        ),
        {
            "username": "test-01",
            "password_hash": password_hash,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    )


def _table_exists(connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()


def _backfill_legacy_rows(connection) -> None:
    conversation_nulls = 0
    material_nulls = 0
    if _table_exists(connection, "tutor_conversations"):
        connection.execute(sa.text("UPDATE tutor_conversations SET user_id = 'test-01' WHERE user_id IS NULL"))
        conversation_nulls = connection.execute(
            sa.text("SELECT COUNT(*) FROM tutor_conversations WHERE user_id IS NULL")
        ).scalar()
    if _table_exists(connection, "study_materials"):
        connection.execute(sa.text("UPDATE study_materials SET user_id = 'test-01' WHERE user_id IS NULL"))
        material_nulls = connection.execute(
            sa.text("SELECT COUNT(*) FROM study_materials WHERE user_id IS NULL")
        ).scalar()
    if conversation_nulls or material_nulls:
        raise RuntimeError("legacy user_id backfill failed; NULL user_id rows remain")


def upgrade() -> None:
    connection = op.get_bind()
    _seed_test_user(connection)
    _backfill_legacy_rows(connection)

    if _table_exists(connection, "tutor_conversations"):
        with op.batch_alter_table("tutor_conversations") as batch_op:
            batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=False)
            batch_op.create_foreign_key(
                "fk_tutor_conversations_user_id_users",
                "users",
                ["user_id"],
                ["username"],
                ondelete="CASCADE",
            )

    if _table_exists(connection, "study_materials"):
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
    connection = op.get_bind()
    if _table_exists(connection, "study_materials"):
        with op.batch_alter_table("study_materials") as batch_op:
            batch_op.drop_constraint("fk_study_materials_user_id_users", type_="foreignkey")
            batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=True)
        connection.execute(sa.text("UPDATE study_materials SET user_id = NULL WHERE user_id = 'test-01'"))

    if _table_exists(connection, "tutor_conversations"):
        with op.batch_alter_table("tutor_conversations") as batch_op:
            batch_op.drop_constraint("fk_tutor_conversations_user_id_users", type_="foreignkey")
            batch_op.alter_column("user_id", existing_type=sa.String(length=100), nullable=True)
        connection.execute(sa.text("UPDATE tutor_conversations SET user_id = NULL WHERE user_id = 'test-01'"))

    connection.execute(sa.text("DELETE FROM users WHERE username = 'test-01'"))
