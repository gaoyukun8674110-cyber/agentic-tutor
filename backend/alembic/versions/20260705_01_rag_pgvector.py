"""Migrate RAG chunks to pgvector.

Revision ID: 20260705_01
Revises: 20260514_04
Create Date: 2026-07-05
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op
from app.config import settings

revision = "20260705_01"
down_revision = "20260514_04"
branch_labels = None
depends_on = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _table_exists(connection, table_name: str) -> bool:
    return table_name in sa.inspect(connection).get_table_names()


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in sa.inspect(connection).get_columns(table_name)}


def _create_material_tables_if_missing(connection) -> None:
    if not _table_exists(connection, "study_materials"):
        op.create_table(
            "study_materials",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("file_type", sa.String(length=20), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("storage_path", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.String(length=50), nullable=False),
            sa.Column("updated_at", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.username"], ondelete="CASCADE"),
        )
        op.create_index("ix_study_materials_id", "study_materials", ["id"])
        op.create_index("ix_study_materials_user_id", "study_materials", ["user_id"])
        op.create_index("ix_study_materials_file_type", "study_materials", ["file_type"])
        op.create_index("ix_study_materials_created_at", "study_materials", ["created_at"])
        op.create_index("ix_study_materials_updated_at", "study_materials", ["updated_at"])

    if not _table_exists(connection, "study_material_chunks"):
        op.create_table(
            "study_material_chunks",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("material_id", sa.Integer(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source_label", sa.String(length=255), nullable=False),
            sa.Column("embedding", Vector(settings.RAG_VECTOR_DIM), nullable=False),
            sa.Column("created_at", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(["material_id"], ["study_materials.id"]),
        )
        op.create_index("ix_study_material_chunks_id", "study_material_chunks", ["id"])
        op.create_index("ix_study_material_chunks_material_id", "study_material_chunks", ["material_id"])
        op.create_index("ix_study_material_chunks_created_at", "study_material_chunks", ["created_at"])


def _backfill_embedding_json(connection) -> None:
    if not _column_exists(connection, "study_material_chunks", "embedding_json"):
        return

    rows = connection.execute(sa.text("SELECT id, material_id, embedding_json FROM study_material_chunks")).all()
    invalid_chunk_ids: list[int] = []
    invalid_material_ids: set[int] = set()
    for row in rows:
        try:
            vector = json.loads(row.embedding_json)
        except (TypeError, json.JSONDecodeError):
            vector = None
        if not isinstance(vector, list) or len(vector) != settings.RAG_VECTOR_DIM:
            invalid_chunk_ids.append(int(row.id))
            invalid_material_ids.add(int(row.material_id))
            continue
        connection.execute(
            sa.text("UPDATE study_material_chunks SET embedding = :embedding WHERE id = :id"),
            {"embedding": str([float(value) for value in vector]), "id": row.id},
        )

    if invalid_chunk_ids:
        connection.execute(
            sa.text("DELETE FROM study_material_chunks WHERE id IN :chunk_ids").bindparams(
                sa.bindparam("chunk_ids", expanding=True)
            ),
            {"chunk_ids": invalid_chunk_ids},
        )
    if invalid_material_ids:
        connection.execute(
            sa.text(
                """
                UPDATE study_materials
                SET status = 'pending',
                    error = 'Embedding dimension mismatch during pgvector migration; re-embedding required',
                    chunk_count = 0,
                    updated_at = :updated_at
                WHERE id IN :material_ids
                """
            ).bindparams(sa.bindparam("material_ids", expanding=True)),
            {"material_ids": list(invalid_material_ids), "updated_at": _now()},
        )


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("pgvector RAG migration requires PostgreSQL")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_material_tables_if_missing(connection)

    if not _column_exists(connection, "study_material_chunks", "embedding"):
        op.add_column(
            "study_material_chunks",
            sa.Column("embedding", Vector(settings.RAG_VECTOR_DIM), nullable=True),
        )
        _backfill_embedding_json(connection)
        op.alter_column("study_material_chunks", "embedding", nullable=False)

    if _column_exists(connection, "study_material_chunks", "embedding_json"):
        op.drop_column("study_material_chunks", "embedding_json")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_study_material_chunks_embedding_hnsw
        ON study_material_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("pgvector RAG migration requires PostgreSQL")

    op.add_column("study_material_chunks", sa.Column("embedding_json", sa.Text(), nullable=True))
    connection.execute(
        sa.text("UPDATE study_material_chunks SET embedding_json = embedding::text WHERE embedding IS NOT NULL")
    )
    op.alter_column("study_material_chunks", "embedding_json", nullable=False)
    op.execute("DROP INDEX IF EXISTS idx_study_material_chunks_embedding_hnsw")
    op.drop_column("study_material_chunks", "embedding")
