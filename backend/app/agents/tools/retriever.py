"""Retriever tool wrapping MaterialService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.services.materials import MaterialService


class RetrieverTool:
    name = "retriever"

    def __init__(self, db: Session, material_service: MaterialService | None = None):
        self.db = db
        self.material_service = material_service

    def search(
        self,
        query: str,
        *,
        user_id: str | None,
        material_ids: list[int] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        material_service = self.material_service or MaterialService(self.db)
        return material_service.search_materials(
            query=query,
            user_id=user_id,
            material_ids=material_ids,
            top_k=top_k,
        )

    def invoke(self, args: dict[str, Any], ctx: Any) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            return {"chunks": [], "error": "query_required"}

        allowed_material_ids = _normalize_positive_ids(getattr(ctx, "material_ids", None))
        if not allowed_material_ids:
            return {"chunks": [], "count": 0, "skipped": "no_selected_materials"}

        requested_material_ids = _normalize_positive_ids(args.get("material_ids"))
        if requested_material_ids:
            allowed_set = set(allowed_material_ids)
            material_ids = [material_id for material_id in requested_material_ids if material_id in allowed_set]
            if not material_ids:
                return {"chunks": [], "count": 0, "skipped": "no_authorized_materials"}
        else:
            material_ids = allowed_material_ids

        chunks = self.search(
            query,
            user_id=getattr(ctx, "user_id", None),
            material_ids=material_ids,
            top_k=int(args.get("top_k") or settings.RAG_TOP_K),
        )
        relevant_chunks = [
            chunk
            for chunk in chunks
            if isinstance(chunk.get("score"), int | float) and float(chunk["score"]) >= settings.RAG_MATERIAL_MIN_SCORE
        ]
        return {"chunks": relevant_chunks, "count": len(relevant_chunks)}


def _normalize_positive_ids(raw_ids: Any) -> list[int]:
    if not isinstance(raw_ids, list):
        return []
    normalized: list[int] = []
    for raw_id in raw_ids:
        try:
            material_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if material_id > 0:
            normalized.append(material_id)
    return normalized
