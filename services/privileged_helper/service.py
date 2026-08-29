"""Fail-closed privileged-helper service boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from personal_ai.contracts import HealthStatus, ToolResult
from personal_ai.permissions import PermissionService


class PrivilegedBackend(Protocol):
    """Backend implemented only by a future audited helper transport."""

    def health(self) -> HealthStatus:
        """Return transport availability without performing privileged work."""

    def invoke(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> ToolResult:
        """Invoke one helper allowlisted action after central authorization."""


class DisabledPrivilegedBackend:
    """Default backend: no elevated process or transport exists in M4."""

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="privileged_helper_backend",
            status="disabled",
            ready=True,
            details={"available": False, "fail_closed": True},
        )

    def invoke(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> ToolResult:
        del parameters
        return ToolResult(
            success=False,
            tool=action,
            action=action,
            target=target,
            summary="The privileged helper is unavailable and the request failed closed.",
            error="privileged_helper_unavailable",
            reversible=False,
            approval_level=3,
        )


@dataclass(slots=True)
class PrivilegedHelperService:
    """Require policy authorization before any future helper transport call."""

    permissions: PermissionService
    backend: PrivilegedBackend
    provider_name: str = "privileged_helper"

    @classmethod
    def create_disabled(cls, permissions: PermissionService) -> PrivilegedHelperService:
        return cls(permissions=permissions, backend=DisabledPrivilegedBackend())

    def health(self) -> HealthStatus:
        backend = self.backend.health()
        policy = self.permissions.policy.privileged_helper
        return HealthStatus(
            name=self.provider_name,
            status="ok",
            ready=True,
            details={
                "boundary_enabled": True,
                "helper_enabled": policy.enabled,
                "transport": policy.transport,
                "endpoint": policy.endpoint,
                "allowed_actions": list(policy.allowed_actions),
                "backend": backend.to_dict(),
                "main_process_administrator_required": False,
                "fail_closed": True,
            },
        )

    def capabilities(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                action.action
                for action in self.permissions.policy.actions.values()
                if action.privileged
            )
        )

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        params = dict(parameters or {})
        approval_id = params.get("approval_id")
        decision = self.permissions.authorize(
            action,
            target=target,
            parameters=params,
            approval_id=approval_id if isinstance(approval_id, str) else None,
        )
        if not decision.allowed:
            return ToolResult(
                success=False,
                tool=action,
                action=action,
                target=target,
                summary="Privileged action was not authorized.",
                data={"permission": decision.to_dict()},
                warnings=("No privileged helper call was made.",),
                error=decision.error,
                reversible=False,
                approval_level=decision.level,
            )
        clean_parameters = self.permissions.sanitized_parameters(params)
        return self.backend.invoke(
            action,
            target=target,
            parameters=clean_parameters,
        )
