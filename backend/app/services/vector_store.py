"""Dialect-aware vector search backends for study-material retrieval."""

from __future__ import annotations

import json
import math
from typing import Protocol

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.materials import StudyMaterial, StudyMaterialChunk


class VectorStore(Protocol):
    def sync_chunks(self, db: Session, chunk_ids: list[int]) -> None: ...

    def search(
        self,
        db: Session,
        *,
        query_vector: list[float],
        top_k: int,
        user_id: str | None,
        material_ids: set[int] | None,
    ) -> list[tuple[int, float]]: ...


def _vector_literal(vector: list[float]) -> str:
    values = []
    for value in vector:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Vector values must be finite numbers")
        values.append(number)
    return json.dumps(values, separators=(",", ":"))


class PgVectorStore:
    """Postgres pgvector-backed search using the derived embedding column."""

    def sync_chunks(self, db: Session, chunk_ids: list[int]) -> None:
        ids = [int(chunk_id) for chunk_id in chunk_ids if chunk_id is not None]
        if not ids:
            return

        statement = text(
            """
            UPDATE study_material_chunks
            SET embedding = CAST(embedding_json AS vector)
            WHERE id IN :chunk_ids
              AND embedding_json IS NOT NULL
              AND embedding_json <> ''
            """
        ).bindparams(bindparam("chunk_ids", expanding=True))
        db.execute(statement, {"chunk_ids": ids})

    def search(
        self,
        db: Session,
        *,
        query_vector: list[float],
        top_k: int,
        user_id: str | None,
        material_ids: set[int] | None,
    ) -> list[tuple[int, float]]:
        if top_k <= 0:
            return []
        if material_ids is not None and not material_ids:
            return []

        filters = ["m.status = 'ready'", "c.embedding IS NOT NULL"]
        params: dict[str, object] = {
            "qvec": _vector_literal(query_vector),
            "top_k": int(top_k),
            "ef_search": int(settings.RAG_HNSW_EF_SEARCH),
        }
        if user_id is not None:
            filters.append("m.user_id = :user_id")
            params["user_id"] = user_id
        if material_ids is not None:
            filters.append("c.material_id IN :material_ids")
            params["material_ids"] = sorted(int(material_id) for material_id in material_ids)

        db.execute(text("SET LOCAL hnsw.ef_search = :ef_search"), params)

        statement = text(
            f"""
            SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
            FROM study_material_chunks c
            JOIN study_materials m ON m.id = c.material_id
            WHERE {" AND ".join(filters)}
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :top_k
            """
        )
        if material_ids is not None:
            statement = statement.bindparams(bindparam("material_ids", expanding=True))

        rows = db.execute(statement, params).all()
        return [
            (int(chunk_id), round(max(0.0, float(score or 0.0)), 6))
            for chunk_id, score in rows
        ]


class BruteForceVectorStore:
    """SQLite and local-development fallback with the same score semantics."""

    def sync_chunks(self, db: Session, chunk_ids: list[int]) -> None:
        return None

    def search(
        self,
        db: Session,
        *,
        query_vector: list[float],
        top_k: int,
        user_id: str | None,
        material_ids: set[int] | None,
    ) -> list[tuple[int, float]]:
        if top_k <= 0:
            return []
        if material_ids is not None and not material_ids:
            return []

        from app.services.materials import cosine_similarity

        query = (
            db.query(StudyMaterialChunk)
            .join(StudyMaterial)
            .filter(StudyMaterial.status == "ready", StudyMaterialChunk.embedding_json.isnot(None))
        )
        if user_id is not None:
            query = query.filter(StudyMaterial.user_id == user_id)
        if material_ids is not None:
            query = query.filter(StudyMaterialChunk.material_id.in_(material_ids))

        scored: list[tuple[int, float]] = []
        for chunk in query.all():
            try:
                raw_vector = json.loads(chunk.embedding_json)
                if not isinstance(raw_vector, list) or not raw_vector:
                    continue
                vector = [float(value) for value in raw_vector]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            score = round(max(0.0, cosine_similarity(query_vector, vector)), 6)
            scored.append((int(chunk.id), score))

        scored.sort(key=lambda entry: (-entry[1], entry[0]))
        return scored[: int(top_k)]


def make_vector_store(db_or_engine) -> VectorStore:
    get_bind = getattr(db_or_engine, "get_bind", None)
    bind = get_bind() if callable(get_bind) else getattr(db_or_engine, "bind", db_or_engine)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name == "postgresql":
        return PgVectorStore()
    return BruteForceVectorStore()
