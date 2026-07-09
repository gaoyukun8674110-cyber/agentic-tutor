"""Shared Agent contracts.

The v2 agent layer is intentionally deterministic: orchestration code chooses
which specialist runs, while specialists can still reuse the existing LLM
gateway and service tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ToolRegistryProtocol(Protocol):
    def get(self, name: str) -> Any: ...

    def has(self, name: str) -> bool: ...


@dataclass(slots=True)
class AgentContext:
    user_id: str
    student_id: int | None = None
    session_id: int | None = None
    material_ids: list[int] | None = None
    learner_snapshot: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    tools: ToolRegistryProtocol | None = None


@dataclass(slots=True)
class AgentResult:
    content: str | None = None
    state_updates: dict[str, Any] = field(default_factory=dict)
    used_tools: list[str] = field(default_factory=list)
    agent_type: str = "agent"
    raw: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    name = "base"
    allowed_tools: list[str] = []

    def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        raise NotImplementedError
