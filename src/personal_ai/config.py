"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the development gateway, Codex, and controlled PC host."""

    app_name: str = "personal-ai-platform"
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    allow_remote: bool = False
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
        )
