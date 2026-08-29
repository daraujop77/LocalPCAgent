import pytest

from personal_ai.config import Settings


def test_settings_have_safe_local_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.allow_remote is False
    assert settings.environment == "development"
    assert settings.qwen_base_url == "http://127.0.0.1:11434/v1"
    assert settings.qwen_model == "qwen3.8:27b"


def test_settings_accept_explicit_environment_overrides() -> None:
    settings = Settings.from_env(
        {
            "PERSONAL_AI_HOST": "10.0.0.5",
            "PERSONAL_AI_PORT": "8123",
            "PERSONAL_AI_ENVIRONMENT": "test",
            "PERSONAL_AI_LOG_LEVEL": "debug",
            "PERSONAL_AI_ALLOW_REMOTE": "true",
            "PERSONAL_AI_API_TOKEN": "remote-secret",
            "PERSONAL_AI_ALLOWED_ORIGINS": "https://pwa.example, http://localhost:3000",
            "PERSONAL_AI_ALLOWED_CLIENT_NETWORKS": "100.64.0.0/10, 192.168.1.0/24",
            "PERSONAL_AI_QWEN_BASE_URL": "http://127.0.0.1:1234/v1",
            "PERSONAL_AI_QWEN_MODEL": "qwen-test",
            "PERSONAL_AI_QWEN_TIMEOUT_SECONDS": "12.5",
            "PERSONAL_AI_QWEN_HEALTH_TIMEOUT_SECONDS": "0.5",
            "PERSONAL_AI_QWEN_API_KEY": "local-secret",
        }
    )

    assert settings.host == "10.0.0.5"
    assert settings.port == 8123
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.allow_remote is True
    assert settings.api_token == "remote-secret"
    assert settings.allowed_origins == ("https://pwa.example", "http://localhost:3000")
    assert settings.allowed_client_networks == ("100.64.0.0/10", "192.168.1.0/24")
    assert settings.qwen_base_url == "http://127.0.0.1:1234/v1"
    assert settings.qwen_model == "qwen-test"
    assert settings.qwen_timeout_seconds == 12.5
    assert settings.qwen_health_timeout_seconds == 0.5
    assert settings.qwen_api_key == "local-secret"


def test_settings_accept_codex_and_pc_overrides() -> None:
    settings = Settings.from_env(
        {
            "PERSONAL_AI_CODEX_EXECUTABLE": "codex-test",
            "PERSONAL_AI_CODEX_TIMEOUT_SECONDS": "45",
            "PERSONAL_AI_PERMISSION_POLICY_PATH": "config/test-permissions.yaml",
            "PERSONAL_AI_PC_WORKSPACE_ROOT": "D:/workspace",
            "PERSONAL_AI_PC_COMMAND_TIMEOUT_SECONDS": "7.5",
        }
    )

    assert settings.codex_executable == "codex-test"
    assert settings.codex_timeout_seconds == 45
    assert settings.permission_policy_path == "config/test-permissions.yaml"
    assert settings.pc_workspace_root == "D:/workspace"
    assert settings.pc_command_timeout_seconds == 7.5


def test_settings_reject_invalid_or_empty_client_networks() -> None:
    with pytest.raises(ValueError, match="valid .*IP networks"):
        Settings.from_env({"PERSONAL_AI_ALLOWED_CLIENT_NETWORKS": "not-a-network"})
    with pytest.raises(ValueError, match="valid .*IP networks"):
        Settings.from_env({"PERSONAL_AI_ALLOWED_CLIENT_NETWORKS": "0.0.0.0/0"})
    with pytest.raises(ValueError, match="must not be empty"):
        Settings.from_env({"PERSONAL_AI_ALLOWED_CLIENT_NETWORKS": "  "})
