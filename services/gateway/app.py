"""Minimal local HTTP gateway with read-only health and discovery endpoints."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from integrations.blender.service import BlenderIntegration
from integrations.pc.service import PcIntegration
from integrations.sc2.service import Sc2Integration
from personal_ai import __version__
from personal_ai.config import Settings
from personal_ai.contracts import HealthStatus, ToolProvider
from services.workflows.service import WorkflowService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GatewayApp:
    settings: Settings
    workflows: WorkflowService
    integrations: tuple[ToolProvider, ...]

    @classmethod
    def create_default(cls, settings: Settings | None = None) -> GatewayApp:
        return cls(
            settings=settings or Settings.from_env(),
            workflows=WorkflowService(),
            integrations=(PcIntegration(), BlenderIntegration(), Sc2Integration()),
        )

    def _checks(self) -> dict[str, HealthStatus]:
        checks = {
            "gateway": HealthStatus(
                name="gateway",
                status="ok",
                ready=True,
                details={"bind": self.settings.host, "port": self.settings.port},
            ),
            "workflows": self.workflows.health(),
        }
        checks.update({provider.provider_name: provider.health() for provider in self.integrations})
        return checks

    def health(self, *, live_only: bool = False) -> dict[str, Any]:
        if live_only:
            return {"status": "ok", "service": self.settings.app_name, "version": __version__}
        checks = self._checks()
        ready = all(check.ready for check in checks.values())
        return {
            "status": "ok" if ready else "degraded",
            "service": self.settings.app_name,
            "version": __version__,
            "environment": self.settings.environment,
            "checks": {name: check.to_dict() for name, check in checks.items()},
        }

    def tool_catalog(self) -> dict[str, Any]:
        return {
            "mode": "discovery-only",
            "providers": [
                {
                    "provider": provider.provider_name,
                    "capabilities": list(provider.capabilities()),
                    "execution": "disabled_in_m0",
                }
                for provider in self.integrations
            ],
        }

    def dispatch(self, method: str, path: str) -> tuple[int, dict[str, Any]]:
        route = urlsplit(path).path
        if method != "GET":
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
        if route == "/":
            return HTTPStatus.OK, {
                "service": self.settings.app_name,
                "version": __version__,
                "message": "Personal AI Platform gateway is running.",
            }
        if route in {"/health", "/health/ready", "/api/v1/health"}:
            payload = self.health()
            status = HTTPStatus.OK if payload["status"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
            return status, payload
        if route == "/health/live":
            return HTTPStatus.OK, self.health(live_only=True)
        if route == "/api/v1/tools":
            return HTTPStatus.OK, self.tool_catalog()
        if route == "/api/v1/runs":
            return HTTPStatus.OK, {"runs": self.workflows.list_runs()}
        return HTTPStatus.NOT_FOUND, {"error": "not_found", "path": route}


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter kept separate so dispatch can be tested without sockets."""

    app: GatewayApp

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("POST")

    def _handle(self, method: str) -> None:
        status, payload = self.app.dispatch(method, self.path)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: object) -> None:
        logger.info("http_request", extra={"http": format_string % args})


def serve(app: GatewayApp) -> None:
    """Run the local gateway until interrupted."""

    bind_host = app.settings.host if app.settings.allow_remote else "127.0.0.1"
    bound_app = app

    class BoundHandler(GatewayRequestHandler):
        app = bound_app

    server = ThreadingHTTPServer((bind_host, app.settings.port), BoundHandler)
    logger.info("gateway_started", extra={"host": bind_host, "port": app.settings.port})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("gateway_stopping")
    finally:
        server.server_close()
