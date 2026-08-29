"""Stable structured contracts shared by gateway and integration boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
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
    data: Mapping[str, object] = field(default_factory=dict)
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
        result["data"] = dict(result["data"])
        return result


@dataclass(frozen=True, slots=True)
class CodingTask:
    """Validated handoff input for an observable repository coding task."""

    task_id: str
    repository_path: str
    task: str
    starting_revision: str | None = None
    constraints: tuple[str, ...] = ()
    test_command: tuple[str, ...] = ()
    test_timeout_seconds: float = 120.0

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["constraints"] = list(self.constraints)
        result["test_command"] = list(self.test_command)
        return result


@dataclass(frozen=True, slots=True)
class TestRun:
    """Result of the bounded test command run after a Codex handoff."""

    command: tuple[str, ...]
    success: bool
    return_code: int | None
    output: str
    duration_ms: int

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["command"] = list(self.command)
        return result


@dataclass(frozen=True, slots=True)
class CodexHandoffResult:
    """Observable result returned by the Codex handoff service."""

    success: bool
    task_id: str
    repository_path: str
    starting_revision: str | None
    ending_revision: str | None
    summary: str
    changed_files: tuple[str, ...] = ()
    tests: tuple[TestRun, ...] = ()
    preexisting_files: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None
    approval_level: ApprovalLevel = 2
    approval: Mapping[str, object] | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "repository_path": self.repository_path,
            "starting_revision": self.starting_revision,
            "ending_revision": self.ending_revision,
            "summary": self.summary,
            "changed_files": list(self.changed_files),
            "tests": [test.to_dict() for test in self.tests],
            "preexisting_files": list(self.preexisting_files),
            "logs": list(self.logs),
            "warnings": list(self.warnings),
            "error": self.error,
            "approval_level": self.approval_level,
            "approval": dict(self.approval) if self.approval else None,
            "duration_ms": self.duration_ms,
        }


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
