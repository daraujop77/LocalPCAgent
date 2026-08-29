"""Development commands for the local M2/M3 gateway."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace

from personal_ai.config import Settings
from personal_ai.logging import configure_logging
from services.gateway.app import GatewayApp, serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Personal AI Platform M2/M3 gateway")
    parser.add_argument("--host", help="override the configured bind host")
    parser.add_argument("--port", type=int, help="override the configured port")
    parser.add_argument("--check", action="store_true", help="print health and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    if args.host is not None or args.port is not None:
        settings = replace(
            settings,
            host=args.host or settings.host,
            port=settings.port if args.port is None else args.port,
        )
    configure_logging(settings.log_level)
    app = GatewayApp.create_default(settings)
    if args.check:
        print(json.dumps(app.health(), indent=2))
        return 0
    serve(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
