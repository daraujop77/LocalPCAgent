"""M0 workflow service boundary; LangGraph is intentionally deferred."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from personal_ai.contracts import HealthStatus


@dataclass(slots=True)
class WorkflowService:
    """In-memory placeholder for a future durable LangGraph-backed service."""

    _runs: list[dict[str, Any]] = field(default_factory=list)

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="workflows",
            status="ok",
            ready=True,
            details={
                "engine": "boundary-only",
                "durability": "not_configured",
                "runs": len(self._runs),
            },
        )

    def list_runs(self) -> list[dict[str, Any]]:
        return list(self._runs)
