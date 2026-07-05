"""Add pgvector embeddings for study material chunks.

Revision ID: 20260705_01
Revises: 20260514_04
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op

revision = "20260705_01"
down_revision = "20260514_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE study_material_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    op.execute(
        """
        UPDATE study_material_chunks
        SET embedding = CAST(embedding_json AS vector)
        WHERE embedding_json IS NOT NULL
          AND embedding_json <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON study_material_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("ALTER TABLE study_material_chunks DROP COLUMN IF EXISTS embedding")
