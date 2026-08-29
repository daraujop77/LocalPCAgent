"""Gateway process entry point for the local M14 platform."""

from personal_ai.config import Settings
from personal_ai.logging import configure_logging
from services.gateway.app import GatewayApp, serve


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    serve(GatewayApp.create_default(settings))


if __name__ == "__main__":
    main()
