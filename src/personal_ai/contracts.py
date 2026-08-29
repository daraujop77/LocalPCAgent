"""Stable structured contracts shared by gateway and integration boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

ApprovalLevel = Literal[0, 1, 2, 3]


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Health information suitable for both API responses and logs."""

    name: str
    status: str
    ready: bool
    details: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "ready": self.ready,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Common result envelope for all future agent tools."""

    success: bool
    tool: str
    action: str
    target: str | None = None
    summary: str = ""
    changed_files: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None
    reversible: bool = True
    approval_level: ApprovalLevel = 0
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for field_name in ("changed_files", "artifacts", "logs", "warnings"):
            result[field_name] = list(result[field_name])
        return result


class ToolProvider(Protocol):
    """Interface implemented by safe, structured tool providers."""

    provider_name: str

    def health(self) -> HealthStatus:
        """Return provider readiness without performing application control."""

    def capabilities(self) -> tuple[str, ...]:
        """Return stable capability names exposed by the provider."""

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        """Execute a structured action or return a structured refusal/error."""
