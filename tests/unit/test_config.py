from personal_ai.config import Settings


def test_settings_have_safe_local_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.allow_remote is False
    assert settings.environment == "development"


def test_settings_accept_explicit_environment_overrides() -> None:
    settings = Settings.from_env(
        {
            "PERSONAL_AI_HOST": "10.0.0.5",
            "PERSONAL_AI_PORT": "8123",
            "PERSONAL_AI_ENVIRONMENT": "test",
            "PERSONAL_AI_LOG_LEVEL": "debug",
            "PERSONAL_AI_ALLOW_REMOTE": "true",
        }
    )

    assert settings.host == "10.0.0.5"
    assert settings.port == 8123
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.allow_remote is True
