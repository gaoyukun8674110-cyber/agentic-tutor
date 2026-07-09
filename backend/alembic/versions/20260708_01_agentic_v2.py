"""Add agentic tutor v2 learner model tables.

Revision ID: 20260708_01
Revises: 20260705_01
Create Date: 2026-07-08
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260708_01"
down_revision = "20260705_01"
branch_labels = None
depends_on = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _table_exists(connection, table_name: str) -> bool:
    return table_name in sa.inspect(connection).get_table_names()


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(connection, table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(connection).get_columns(table_name)}


def _create_tables(connection) -> None:
    if not _table_exists(connection, "skills"):
        op.create_table(
            "skills",
            sa.Column("skill_id", sa.String(length=100), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("chapter", sa.String(length=100), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
        )

    if not _table_exists(connection, "skill_edges"):
        op.create_table(
            "skill_edges",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("from_skill_id", sa.String(length=100), nullable=False),
            sa.Column("to_skill_id", sa.String(length=100), nullable=False),
            sa.Column("relation", sa.String(length=50), nullable=False, server_default="prerequisite"),
            sa.ForeignKeyConstraint(["from_skill_id"], ["skills.skill_id"]),
            sa.ForeignKeyConstraint(["to_skill_id"], ["skills.skill_id"]),
        )
        op.create_index("ix_skill_edges_id", "skill_edges", ["id"])
        op.create_index("ix_skill_edges_from_skill_id", "skill_edges", ["from_skill_id"])
        op.create_index("ix_skill_edges_to_skill_id", "skill_edges", ["to_skill_id"])

    if not _table_exists(connection, "learner_profiles"):
        op.create_table(
            "learner_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("learning_style", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("review_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("review_frequency", sa.String(length=50), nullable=False, server_default="weekly"),
            sa.Column("confidence_calibration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("updated_at", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
            sa.UniqueConstraint("student_id"),
        )
        op.create_index("ix_learner_profiles_id", "learner_profiles", ["id"])
        op.create_index("ix_learner_profiles_student_id", "learner_profiles", ["student_id"])

    if not _table_exists(connection, "review_reports"):
        op.create_table(
            "review_reports",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("period", sa.String(length=100), nullable=False),
            sa.Column("report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.String(length=50), nullable=False),
            sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        )
        op.create_index("ix_review_reports_id", "review_reports", ["id"])
        op.create_index("ix_review_reports_student_id", "review_reports", ["student_id"])
        op.create_index("ix_review_reports_period", "review_reports", ["period"])


def _add_mastery_columns(connection) -> None:
    if not _column_exists(connection, "student_masteries", "bkt_p_known"):
        op.add_column("student_masteries", sa.Column("bkt_p_known", sa.Float(), nullable=True))
    if not _column_exists(connection, "student_masteries", "bkt_half_life"):
        op.add_column("student_masteries", sa.Column("bkt_half_life", sa.Float(), nullable=True))
    if not _column_exists(connection, "student_masteries", "last_decay_at"):
        op.add_column("student_masteries", sa.Column("last_decay_at", sa.String(length=50), nullable=True))


def _backfill_skills(connection) -> None:
    if not _table_exists(connection, "question_skills"):
        return

    connection.execute(
        sa.text(
            """
            INSERT INTO skills (skill_id, name, chapter, description)
            SELECT DISTINCT qs.skill_id, qs.skill_name, q.chapter, NULL
            FROM question_skills qs
            LEFT JOIN questions q ON q.id = qs.question_id
            WHERE qs.skill_id IS NOT NULL
            ON CONFLICT (skill_id) DO NOTHING
            """
        )
    )

    if _table_exists(connection, "prerequisite_skills"):
        connection.execute(
            sa.text(
                """
                INSERT INTO skills (skill_id, name, chapter, description)
                SELECT DISTINCT ps.prerequisite_skill_id, ps.prerequisite_skill_id, NULL, NULL
                FROM prerequisite_skills ps
                WHERE ps.prerequisite_skill_id IS NOT NULL
                ON CONFLICT (skill_id) DO NOTHING
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO skill_edges (from_skill_id, to_skill_id, relation)
                SELECT DISTINCT ps.prerequisite_skill_id, qs.skill_id, 'prerequisite'
                FROM prerequisite_skills ps
                JOIN question_skills qs ON qs.question_id = ps.question_id
                WHERE ps.prerequisite_skill_id IS NOT NULL
                  AND qs.skill_id IS NOT NULL
                  AND ps.prerequisite_skill_id <> qs.skill_id
                  AND NOT EXISTS (
                    SELECT 1 FROM skill_edges se
                    WHERE se.from_skill_id = ps.prerequisite_skill_id
                      AND se.to_skill_id = qs.skill_id
                      AND se.relation = 'prerequisite'
                  )
                """
            )
        )


def _backfill_profiles(connection) -> None:
    if not _table_exists(connection, "students"):
        return
    connection.execute(
        sa.text(
            """
            INSERT INTO learner_profiles
                (student_id, learning_style, review_enabled, review_frequency, confidence_calibration, updated_at)
            SELECT id, '{}', TRUE, 'weekly', '{}', :updated_at
            FROM students
            WHERE NOT EXISTS (
                SELECT 1 FROM learner_profiles lp WHERE lp.student_id = students.id
            )
            """
        ),
        {"updated_at": _now()},
    )


def upgrade() -> None:
    connection = op.get_bind()
    # The `students` table (and the rest of the base schema this migration
    # builds on: student_masteries, question_skills, questions, ...) is created
    # by the application's SQLAlchemy create_all() bootstrap, never by Alembic.
    # When Alembic runs against a fresh database — e.g. CI's `alembic upgrade
    # head` smoke test, which executes before the app boots — those base tables
    # do not exist yet, so the FKs below cannot be created. In that case there
    # is nothing to migrate: create_all() will build the full current schema
    # (including every table and column this migration adds, all of which are
    # registered models) at app startup.
    if not _table_exists(connection, "students"):
        return
    _create_tables(connection)
    _add_mastery_columns(connection)
    _backfill_skills(connection)
    _backfill_profiles(connection)


def downgrade() -> None:
    connection = op.get_bind()
    for column_name in ["last_decay_at", "bkt_half_life", "bkt_p_known"]:
        if _column_exists(connection, "student_masteries", column_name):
            op.drop_column("student_masteries", column_name)

    for table_name in ["review_reports", "learner_profiles", "skill_edges", "skills"]:
        if _table_exists(connection, table_name):
            op.drop_table(table_name)
