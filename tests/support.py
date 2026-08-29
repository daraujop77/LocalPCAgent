from collections.abc import Sequence
from pathlib import Path

from integrations.pc.host import PcExecution
from personal_ai.chat import ChatMessage
from personal_ai.contracts import HealthStatus
from personal_ai.permissions import PermissionService
from personal_ai.qwen import ModelReply
from services.codex.service import CodexBackendResult

POLICY_PATH = Path(__file__).parents[1] / "policies" / "permissions.yaml"


def make_permission_service(*, clock=None) -> PermissionService:
    return PermissionService.from_path(POLICY_PATH, clock=clock)


class FakeQwenClient:
    route_name = "qwen-local"
    model_name = "qwen-test"

    def __init__(self, response: str = "Fake Qwen response") -> None:
        self.response = response
        self.calls: list[tuple[ChatMessage, ...]] = []

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="qwen",
            status="ok",
            ready=True,
            details={"backend": "fake", "model": self.model_name},
        )

    def complete(self, messages: Sequence[ChatMessage], *, request_id: str) -> ModelReply:
        del request_id
        self.calls.append(tuple(messages))
        return ModelReply(content=self.response, model_name=self.model_name)


class FakeCodexBackend:
    """Deterministic backend used to exercise handoff observation without a live agent."""

    def __init__(self) -> None:
        self.calls = []

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="codex",
            status="ok",
            ready=True,
            details={"backend": "fake", "available": True},
        )

    def run(self, task) -> CodexBackendResult:
        self.calls.append(task)
        marker = Path(task.repository_path) / "codex-handoff.txt"
        marker.write_text("changed by fake Codex\n", encoding="utf-8")
        return CodexBackendResult(
            success=True,
            summary="Fake Codex applied the requested fixture change.",
            logs=("fake_codex_completed",),
        )


class FakePcBackend:
    """Deterministic PC backend for gateway routing tests."""

    def __init__(self) -> None:
        self.calls = []

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="pc",
            status="ok",
            ready=True,
            details={"backend": "fake", "control_enabled": True},
        )

    def execute(self, action, *, target=None, parameters=None) -> PcExecution:
        self.calls.append((action, target, parameters or {}))
        return PcExecution(
            success=True,
            summary=f"Fake PC executed {action}.",
            data={"action": action},
            logs=("fake_pc_completed",),
        )
