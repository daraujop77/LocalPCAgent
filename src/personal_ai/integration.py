"""Shared safe base for M0 application integration skeletons."""

from __future__ import annotations

from collections.abc import Mapping

from personal_ai.contracts import HealthStatus, ToolResult


class SkeletonIntegration:
    """Advertise a future integration without touching the host application."""

    provider_name = "integration"
    _capabilities: tuple[str, ...] = ()

    def health(self) -> HealthStatus:
        return HealthStatus(
            name=self.provider_name,
            status="ok",
            ready=True,
            details={
                "mode": "skeleton",
                "implemented_actions": [],
                "control_enabled": False,
            },
        )

    def capabilities(self) -> tuple[str, ...]:
        return self._capabilities

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        del parameters
        tool_name = f"{self.provider_name}.{action}"
        return ToolResult(
            success=False,
            tool=tool_name,
            action=action,
            target=target,
            summary=f"{tool_name} is defined but not implemented in M0",
            warnings=("No host application or PC control was invoked.",),
            error="not_implemented",
            reversible=True,
            approval_level=0,
        )
