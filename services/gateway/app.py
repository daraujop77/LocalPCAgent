"""Minimal local HTTP gateway with health, discovery, and local chat endpoints."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from integrations.blender.service import BlenderIntegration
from integrations.pc.service import PcIntegration
from integrations.sc2.service import Sc2Integration
from personal_ai import __version__
from personal_ai.chat import ChatRequest, ChatValidationError
from personal_ai.config import Settings
from personal_ai.contracts import HealthStatus, ToolProvider
from personal_ai.hermes import HermesService
from personal_ai.qwen import HttpQwenClient, ModelClient
from personal_ai.router import ModelRouter
from services.codex.service import (
    CodexHandoffService,
    CodingTaskValidationError,
    SubprocessCodexBackend,
    coding_task_from_payload,
)
from services.workflows.service import WorkflowService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GatewayApp:
    settings: Settings
    workflows: WorkflowService
    integrations: tuple[ToolProvider, ...]
    hermes: HermesService
    codex: CodexHandoffService
    pc: PcIntegration

    @classmethod
    def create_default(
        cls,
        settings: Settings | None = None,
        model_client: ModelClient | None = None,
    ) -> GatewayApp:
        resolved_settings = settings or Settings.from_env()
        pc = PcIntegration(
            workspace_root=resolved_settings.pc_workspace_root,
            allowed_applications=resolved_settings.pc_allowed_applications,
            command_timeout_seconds=resolved_settings.pc_command_timeout_seconds,
        )
        return cls(
            settings=resolved_settings,
            workflows=WorkflowService(),
            integrations=(pc, BlenderIntegration(), Sc2Integration()),
            hermes=HermesService(model_client or HttpQwenClient(resolved_settings), ModelRouter()),
            codex=CodexHandoffService(
                SubprocessCodexBackend(
                    executable=resolved_settings.codex_executable,
                    timeout_seconds=resolved_settings.codex_timeout_seconds,
                )
            ),
            pc=pc,
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
            "hermes": self.hermes.health(),
            "codex": self.codex.health(),
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
            "mode": "controlled-local-execution",
            "hermes": {"capabilities": ["hermes.chat"], "execution": "enabled_local_qwen"},
            "codex": {
                "capabilities": ["codex.repository_handoff"],
                "execution": "enabled_if_cli_available",
            },
            "providers": [
                {
                    "provider": provider.provider_name,
                    "capabilities": list(provider.capabilities()),
                    "execution": (
                        "enabled_controlled_allowlisted"
                        if provider.provider_name == "pc"
                        else "disabled_until_future_milestone"
                    ),
                }
                for provider in self.integrations
            ],
        }

    def dispatch(
        self,
        method: str,
        path: str,
        body: bytes | Mapping[str, object] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        route = urlsplit(path).path
        if route == "/api/v1/chat":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_chat(body)
        if route == "/api/v1/codex/handoff":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_codex(body)
        if route == "/api/v1/pc/invoke":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_pc(body)
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
        if route == "/api/v1/codex/health":
            check = self.codex.health()
            status = HTTPStatus.OK if check.ready else HTTPStatus.SERVICE_UNAVAILABLE
            return status, check.to_dict()
        if route == "/api/v1/codex/runs":
            return HTTPStatus.OK, {"runs": self.codex.list_runs()}
        if route == "/api/v1/pc/health":
            check = self.pc.health()
            status = HTTPStatus.OK if check.ready else HTTPStatus.SERVICE_UNAVAILABLE
            return status, check.to_dict()
        if route == "/api/v1/runs":
            return HTTPStatus.OK, {"runs": self.workflows.list_runs()}
        return HTTPStatus.NOT_FOUND, {"error": "not_found", "path": route}

    def _dispatch_chat(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            if isinstance(body, (bytes, bytearray)):
                payload = json.loads(body.decode("utf-8"))
            else:
                payload = body
            request = ChatRequest.from_payload(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ChatValidationError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }

        response = self.hermes.chat(request)
        status = HTTPStatus.OK if response.success else HTTPStatus.SERVICE_UNAVAILABLE
        return status, response.to_dict()

    def _dispatch_codex(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            task, approval_granted = coding_task_from_payload(self._decode_body(body))
        except (UnicodeDecodeError, json.JSONDecodeError, CodingTaskValidationError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }
        response = self.codex.delegate(task, approval_granted=approval_granted)
        if response.success:
            status = HTTPStatus.OK
        elif response.error == "approval_required":
            status = HTTPStatus.CONFLICT
        elif response.error == "codex_unavailable":
            status = HTTPStatus.SERVICE_UNAVAILABLE
        else:
            status = HTTPStatus.UNPROCESSABLE_ENTITY
        return status, response.to_dict()

    def _dispatch_pc(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = self._decode_body(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }
        if not isinstance(payload, Mapping):
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": "request body must be a JSON object",
            }
        action = payload.get("action")
        target = payload.get("target")
        parameters = payload.get("parameters", {})
        if not isinstance(action, str) or not action.strip():
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": "action must be a non-empty string",
            }
        if target is not None and not isinstance(target, str):
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": "target must be a string when provided",
            }
        if not isinstance(parameters, Mapping):
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": "parameters must be a JSON object",
            }
        result = self.pc.invoke(action.strip(), target=target, parameters=parameters)
        status = (
            HTTPStatus.OK
            if result.success
            else HTTPStatus.CONFLICT
            if result.error == "approval_required"
            else HTTPStatus.UNPROCESSABLE_ENTITY
        )
        return status, result.to_dict()

    @staticmethod
    def _decode_body(body: bytes | Mapping[str, object] | None) -> object:
        if isinstance(body, (bytes, bytearray)):
            return json.loads(body.decode("utf-8"))
        return body


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter kept separate so dispatch can be tested without sockets."""

    app: GatewayApp

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("POST")

    def _handle(self, method: str) -> None:
        body = None
        if method == "POST":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            body = self.rfile.read(content_length)
        status, payload = self.app.dispatch(method, self.path, body)
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
