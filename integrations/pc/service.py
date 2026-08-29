"""Controlled Windows PC integration for M3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from integrations.pc.host import NativeWindowsPcControl, PcControlBackend, PcExecution
from personal_ai.contracts import ApprovalLevel, HealthStatus, ToolResult


class PcIntegration:
    """Expose allowlisted host primitives with explicit mutation boundaries."""

    provider_name = "pc"
    _capabilities = (
        "pc.system_info",
        "pc.list_processes",
        "pc.apps.list",
        "pc.apps.launch",
        "pc.apps.focus",
        "pc.apps.close",
        "pc.files.read",
        "pc.files.copy",
        "pc.files.move",
        "pc.files.patch",
        "pc.files.snapshot",
        "pc.shell.powershell",
        "pc.window.list",
        "pc.window.focus",
        "pc.screen.capture",
        "pc.input.click",
        "pc.input.drag",
        "pc.input.type",
        "pc.input.hotkey",
        "pc.input.scroll",
    )
    _approval_levels: dict[str, ApprovalLevel] = {
        "pc.system_info": 0,
        "pc.list_processes": 0,
        "pc.apps.list": 0,
        "pc.apps.launch": 1,
        "pc.apps.focus": 1,
        "pc.apps.close": 2,
        "pc.files.read": 0,
        "pc.files.copy": 1,
        "pc.files.move": 2,
        "pc.files.patch": 2,
        "pc.files.snapshot": 1,
        "pc.shell.powershell": 2,
        "pc.window.list": 0,
        "pc.window.focus": 1,
        "pc.screen.capture": 0,
        "pc.input.click": 2,
        "pc.input.drag": 2,
        "pc.input.type": 2,
        "pc.input.hotkey": 2,
        "pc.input.scroll": 2,
    }

    def __init__(
        self,
        workspace_root: str | None = None,
        allowed_applications: Sequence[str] = ("notepad.exe", "calc.exe", "mspaint.exe"),
        command_timeout_seconds: float = 30.0,
        backend: PcControlBackend | None = None,
    ) -> None:
        self._backend = backend or NativeWindowsPcControl(
            workspace_root=workspace_root,
            allowed_applications=allowed_applications,
            command_timeout_seconds=command_timeout_seconds,
        )

    def health(self) -> HealthStatus:
        return self._backend.health()

    def capabilities(self) -> tuple[str, ...]:
        return self._capabilities

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        params = parameters or {}
        if action not in self._approval_levels:
            return ToolResult(
                success=False,
                tool=f"pc.{action}" if not action.startswith("pc.") else action,
                action=action,
                target=target,
                summary=f"PC action {action} is not allowlisted.",
                error="unsupported_action",
                approval_level=0,
            )
        approval_level = self._approval_levels[action]
        if approval_level >= 2 and params.get("approval_granted") is not True:
            return ToolResult(
                success=False,
                tool=action,
                action=action,
                target=target,
                summary=f"{action} requires explicit approval before execution.",
                warnings=("No host operation was invoked.",),
                error="approval_required",
                reversible=action.startswith("pc.input."),
                approval_level=approval_level,
            )
        execution = self._backend.execute(action, target=target, parameters=params)
        return self._to_result(action, target, approval_level, execution)

    @staticmethod
    def _to_result(
        action: str,
        target: str | None,
        approval_level: ApprovalLevel,
        execution: PcExecution,
    ) -> ToolResult:
        return ToolResult(
            success=execution.success,
            tool=action,
            action=action,
            target=target,
            summary=execution.summary,
            changed_files=execution.changed_files,
            artifacts=execution.artifacts,
            data=dict(execution.data or {}),
            logs=execution.logs,
            warnings=execution.warnings,
            error=execution.error,
            reversible=execution.reversible,
            approval_level=approval_level,
            duration_ms=execution.duration_ms,
        )
