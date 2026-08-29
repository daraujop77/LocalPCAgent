"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("PERSONAL_AI_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PERSONAL_AI_PORT must be between 1 and 65535")
    return port


def _parse_positive_float(value: str, *, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_client_networks(value: str) -> tuple[str, ...]:
    networks = _parse_csv(value)
    if not networks:
        raise ValueError("PERSONAL_AI_ALLOWED_CLIENT_NETWORKS must not be empty")
    parsed: list[str] = []
    for network in networks:
        try:
            parsed_network = ipaddress.ip_network(network, strict=False)
            if (
                parsed_network.is_global
                or parsed_network.is_multicast
                or parsed_network.is_unspecified
            ):
                raise ValueError("network is publicly routable or reserved")
            parsed.append(str(parsed_network))
        except ValueError as exc:
            raise ValueError(
                "PERSONAL_AI_ALLOWED_CLIENT_NETWORKS must contain valid non-public IP networks"
            ) from exc
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the local gateway and bounded integration services."""

    app_name: str = "personal-ai-platform"
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    allow_remote: bool = False
    api_token: str | None = None
    allowed_origins: tuple[str, ...] = ()
    allowed_client_networks: tuple[str, ...] = ("127.0.0.1/32",)
    qwen_base_url: str = "http://127.0.0.1:11434/v1"
    qwen_model: str = "qwen3.8:27b"
    qwen_timeout_seconds: float = 60.0
    qwen_health_timeout_seconds: float = 2.0
    qwen_api_key: str | None = None
    codex_executable: str = "codex"
    codex_timeout_seconds: float = 900.0
    permission_policy_path: str = "policies/permissions.yaml"
    pc_workspace_root: str = "."
    pc_command_timeout_seconds: float = 30.0
    blender_executable: str | None = None
    blender_command_timeout_seconds: float = 300.0
    sc2_workspace_root: str = "."
    artifact_root: str = "artifacts"
    memory_root: str = "memory"
    workflow_storage_root: str = "artifacts/workflows"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        return cls(
            host=values.get("PERSONAL_AI_HOST", "127.0.0.1"),
            port=_parse_port(values.get("PERSONAL_AI_PORT", "8000")),
            environment=values.get("PERSONAL_AI_ENVIRONMENT", "development"),
            log_level=values.get("PERSONAL_AI_LOG_LEVEL", "INFO").upper(),
            allow_remote=_parse_bool(
                values.get("PERSONAL_AI_ALLOW_REMOTE", "false"),
                name="PERSONAL_AI_ALLOW_REMOTE",
            ),
            api_token=values.get("PERSONAL_AI_API_TOKEN") or None,
            allowed_origins=_parse_csv(values.get("PERSONAL_AI_ALLOWED_ORIGINS", "")),
            allowed_client_networks=_parse_client_networks(
                values.get("PERSONAL_AI_ALLOWED_CLIENT_NETWORKS", "127.0.0.1/32")
            ),
            qwen_base_url=values.get("PERSONAL_AI_QWEN_BASE_URL", "http://127.0.0.1:11434/v1"),
            qwen_model=values.get("PERSONAL_AI_QWEN_MODEL", "qwen3.8:27b"),
            qwen_timeout_seconds=_parse_positive_float(
                values.get("PERSONAL_AI_QWEN_TIMEOUT_SECONDS", "60"),
                name="PERSONAL_AI_QWEN_TIMEOUT_SECONDS",
            ),
            qwen_health_timeout_seconds=_parse_positive_float(
                values.get("PERSONAL_AI_QWEN_HEALTH_TIMEOUT_SECONDS", "2"),
                name="PERSONAL_AI_QWEN_HEALTH_TIMEOUT_SECONDS",
            ),
            qwen_api_key=values.get("PERSONAL_AI_QWEN_API_KEY") or None,
            codex_executable=values.get("PERSONAL_AI_CODEX_EXECUTABLE", "codex"),
            codex_timeout_seconds=_parse_positive_float(
                values.get("PERSONAL_AI_CODEX_TIMEOUT_SECONDS", "900"),
                name="PERSONAL_AI_CODEX_TIMEOUT_SECONDS",
            ),
            permission_policy_path=values.get(
                "PERSONAL_AI_PERMISSION_POLICY_PATH",
                "policies/permissions.yaml",
            ),
            pc_workspace_root=values.get("PERSONAL_AI_PC_WORKSPACE_ROOT", "."),
            pc_command_timeout_seconds=_parse_positive_float(
                values.get("PERSONAL_AI_PC_COMMAND_TIMEOUT_SECONDS", "30"),
                name="PERSONAL_AI_PC_COMMAND_TIMEOUT_SECONDS",
            ),
            blender_executable=values.get("PERSONAL_AI_BLENDER_EXECUTABLE") or None,
            blender_command_timeout_seconds=_parse_positive_float(
                values.get("PERSONAL_AI_BLENDER_COMMAND_TIMEOUT_SECONDS", "300"),
                name="PERSONAL_AI_BLENDER_COMMAND_TIMEOUT_SECONDS",
            ),
            sc2_workspace_root=values.get("PERSONAL_AI_SC2_WORKSPACE_ROOT", "."),
            artifact_root=values.get("PERSONAL_AI_ARTIFACT_ROOT", "artifacts"),
            memory_root=values.get("PERSONAL_AI_MEMORY_ROOT", "memory"),
            workflow_storage_root=values.get(
                "PERSONAL_AI_WORKFLOW_STORAGE_ROOT",
                "artifacts/workflows",
            ),
        )
