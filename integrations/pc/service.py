"""Controlled Windows PC integration governed by the M4 permission service."""

from __future__ import annotations

from collections.abc import Mapping

from integrations.pc.host import NativeWindowsPcControl, PcControlBackend, PcExecution
from personal_ai.contracts import HealthStatus, ToolResult
from personal_ai.permissions import PermissionDecision, PermissionService


class PcIntegration:
    """Expose native host primitives only after centralized authorization."""

    provider_name = "pc"
    _supported_actions = (
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

    def __init__(
        self,
        permissions: PermissionService,
        *,
        workspace_root: str | None = None,
        command_timeout_seconds: float = 30.0,
        backend: PcControlBackend | None = None,
    ) -> None:
        self.permissions = permissions
        configured_actions = {
            action for action in permissions.policy.actions if action.startswith("pc.")
        }
        if configured_actions != set(self._supported_actions):
            raise ValueError("PC action policy must exactly match the supported M4 actions")
        self._backend = backend or NativeWindowsPcControl(
            workspace_root=workspace_root,
            allowed_applications=permissions.policy.pc.applications,
            allowed_powershell_verbs=permissions.policy.pc.powershell_verbs,
            command_timeout_seconds=command_timeout_seconds,
        )

    def health(self) -> HealthStatus:
        backend = self._backend.health()
        details = dict(backend.details)
        details.update(
            {
                "permission_policy": self.permissions.policy.source,
                "central_authorization": True,
            }
        )
        return HealthStatus(
            name=backend.name,
            status=backend.status,
            ready=backend.ready,
            details=details,
        )

    def capabilities(self) -> tuple[str, ...]:
        return self._supported_actions

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        params = dict(parameters or {})
        raw_approval_id = params.get("approval_id")
        if raw_approval_id is not None and not isinstance(raw_approval_id, str):
            return ToolResult(
                success=False,
                tool=action,
                action=action,
                target=target,
                summary="approval_id must be a string.",
                error="invalid_approval_id",
                approval_level=0,
            )
        decision = self.permissions.authorize(
            action,
            target=target,
            parameters=params,
            approval_id=raw_approval_id,
        )
        if not decision.allowed:
            return ToolResult(
                success=False,
                tool=action,
                action=action,
                target=target,
                summary=f"{action} was not authorized by the M4 permission policy.",
                data={"permission": decision.to_dict()},
                warnings=("No host operation was invoked.",),
                error=decision.error,
                reversible=action.startswith("pc.input."),
                approval_level=decision.level,
            )
        clean_parameters = self.permissions.sanitized_parameters(params)
        execution = self._backend.execute(
            action,
            target=target,
            parameters=clean_parameters,
        )
        return self._to_result(action, target, decision, execution)

    @staticmethod
    def _to_result(
        action: str,
        target: str | None,
        decision: PermissionDecision,
        execution: PcExecution,
    ) -> ToolResult:
        data = dict(execution.data or {})
        data["permission"] = decision.to_dict()
        return ToolResult(
            success=execution.success,
            tool=action,
            action=action,
            target=target,
            summary=execution.summary,
            changed_files=execution.changed_files,
            artifacts=execution.artifacts,
            data=data,
            logs=execution.logs,
            warnings=execution.warnings,
            error=execution.error,
            reversible=execution.reversible,
            approval_level=decision.level,
            duration_ms=execution.duration_ms,
        )
