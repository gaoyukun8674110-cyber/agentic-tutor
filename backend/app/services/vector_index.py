"""Persistent vector index utilities for study-material retrieval."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VectorIndexItem:
    chunk_id: int
    material_id: int
    user_id: str | None
    vector: list[float]


def euclidean_distance(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return float("inf")
    return math.sqrt(sum((a - b) * (a - b) for a, b in zip(left, right, strict=False)))


def _build_tree(items: list[VectorIndexItem]) -> dict | None:
    if not items:
        return None

    vantage_point = items[-1]
    if len(items) == 1:
        return {
            "chunk_id": vantage_point.chunk_id,
            "threshold": 0.0,
            "left": None,
            "right": None,
        }

    remaining = items[:-1]
    distances = [(euclidean_distance(vantage_point.vector, item.vector), item) for item in remaining]
    distances.sort(key=lambda entry: entry[0])
    threshold = distances[len(distances) // 2][0]
    inner = [item for distance, item in distances if distance <= threshold]
    outer = [item for distance, item in distances if distance > threshold]
    return {
        "chunk_id": vantage_point.chunk_id,
        "threshold": round(threshold, 8),
        "left": _build_tree(inner),
        "right": _build_tree(outer),
    }


def build_snapshot(
    items: Iterable[VectorIndexItem],
    *,
    embedding_mode: str,
    ready_chunk_count: int,
    max_chunk_id: int,
) -> dict:
    indexed_items = list(items)
    global_tree = _build_tree(indexed_items)

    user_trees: dict[str, dict | None] = {}
    user_groups: dict[str, list[VectorIndexItem]] = {}
    for item in indexed_items:
        if item.user_id:
            user_groups.setdefault(item.user_id, []).append(item)
    for user_id, user_items in user_groups.items():
        user_trees[user_id] = _build_tree(user_items)

    return {
        "version": 1,
        "embedding_mode": embedding_mode,
        "ready_chunk_count": ready_chunk_count,
        "max_chunk_id": max_chunk_id,
        "items": {
            str(item.chunk_id): {
                "chunk_id": item.chunk_id,
                "material_id": item.material_id,
                "user_id": item.user_id,
                "vector": item.vector,
            }
            for item in indexed_items
        },
        "global_tree": global_tree,
        "user_trees": user_trees,
    }


class PersistentVectorIndex:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, snapshot: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)


def search_snapshot(
    snapshot: dict,
    *,
    query_vector: list[float],
    top_k: int,
    user_id: str | None = None,
    material_ids: set[int] | None = None,
    allowed_user_ids: set[str | None] | None = None,
) -> list[tuple[int, float]]:
    if top_k <= 0:
        return []

    items = {
        int(chunk_id): VectorIndexItem(
            chunk_id=int(payload["chunk_id"]),
            material_id=int(payload["material_id"]),
            user_id=payload.get("user_id"),
            vector=[float(value) for value in payload.get("vector", [])],
        )
        for chunk_id, payload in snapshot.get("items", {}).items()
    }
    if not items:
        return []

    tree = snapshot.get("user_trees", {}).get(user_id) if user_id else snapshot.get("global_tree")
    if not tree:
        return []

    results: list[tuple[int, float]] = []

    def predicate(item: VectorIndexItem) -> bool:
        if allowed_user_ids is not None and item.user_id not in allowed_user_ids:
            return False
        if material_ids is not None and item.material_id not in material_ids:
            return False
        return True

    def tau() -> float:
        if len(results) < top_k:
            return float("inf")
        return results[-1][1]

    def consider(item: VectorIndexItem, distance: float) -> None:
        if not predicate(item) or math.isinf(distance):
            return
        results.append((item.chunk_id, distance))
        results.sort(key=lambda entry: entry[1])
        del results[top_k:]

    def walk(node: dict | None) -> None:
        if not node:
            return

        item = items.get(int(node["chunk_id"]))
        if item is None:
            return

        distance = euclidean_distance(query_vector, item.vector)
        consider(item, distance)

        threshold = float(node.get("threshold") or 0.0)
        left = node.get("left")
        right = node.get("right")

        if distance < threshold:
            walk(left)
            if distance + tau() >= threshold:
                walk(right)
        else:
            walk(right)
            if distance - tau() <= threshold:
                walk(left)

    walk(tree)
    return results
