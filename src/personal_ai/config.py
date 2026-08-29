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


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for the development gateway."""

    app_name: str = "personal-ai-platform"
    host: str = "127.0.0.1"
    port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    allow_remote: bool = False

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
        )
