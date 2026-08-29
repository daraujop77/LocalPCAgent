"""Minimal local HTTP gateway with health, discovery, and local chat endpoints."""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from integrations.blender.service import BlenderIntegration
from integrations.pc.service import PcIntegration
from integrations.sc2.service import Sc2Integration
from personal_ai import __version__
from personal_ai.chat import ChatRequest, ChatValidationError
from personal_ai.config import Settings
from personal_ai.contracts import HealthStatus, ToolProvider
from personal_ai.hermes import HermesService
from personal_ai.memory import MemoryService
from personal_ai.permissions import PermissionService, PermissionServiceError
from personal_ai.qwen import HttpQwenClient, ModelClient
from personal_ai.router import ModelRouter
from services.codex.service import (
    CodexHandoffService,
    CodingTaskValidationError,
    SubprocessCodexBackend,
    coding_task_from_payload,
)
from services.gateway.artifacts import ArtifactCatalog
from services.privileged_helper.service import PrivilegedHelperService
from services.workflows.definitions import blender_workflow, sc2_workflow
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
    permissions: PermissionService
    privileged: PrivilegedHelperService
    memory: MemoryService | None = None

    @classmethod
    def create_default(
        cls,
        settings: Settings | None = None,
        model_client: ModelClient | None = None,
    ) -> GatewayApp:
        resolved_settings = settings or Settings.from_env()
        permissions = PermissionService.from_path(resolved_settings.permission_policy_path)
        pc = PcIntegration(
            permissions,
            workspace_root=resolved_settings.pc_workspace_root,
            command_timeout_seconds=resolved_settings.pc_command_timeout_seconds,
        )
        privileged = PrivilegedHelperService.create_disabled(permissions)
        codex = CodexHandoffService(
            SubprocessCodexBackend(
                executable=resolved_settings.codex_executable,
                timeout_seconds=resolved_settings.codex_timeout_seconds,
            ),
            permissions,
        )
        memory = MemoryService(resolved_settings.memory_root)
        hermes = HermesService(
            model_client or HttpQwenClient(resolved_settings),
            ModelRouter(),
            codex=codex,
            memory=memory,
        )
        blender = BlenderIntegration(
            permissions,
            workspace_root=resolved_settings.pc_workspace_root,
            artifact_root=resolved_settings.artifact_root,
            executable=resolved_settings.blender_executable,
            timeout_seconds=resolved_settings.blender_command_timeout_seconds,
        )
        sc2 = Sc2Integration(
            permissions,
            workspace_root=resolved_settings.sc2_workspace_root,
            artifact_root=resolved_settings.artifact_root,
        )
        workflows = WorkflowService(resolved_settings.workflow_storage_root, memory=memory)
        workflows.register(blender_workflow(blender, memory))
        workflows.register(sc2_workflow(sc2, memory))
        workflows.recover_incomplete()
        return cls(
            settings=resolved_settings,
            workflows=workflows,
            integrations=(pc, blender, sc2),
            hermes=hermes,
            codex=codex,
            pc=pc,
            permissions=permissions,
            privileged=privileged,
            memory=memory,
        )

    def _checks(self) -> dict[str, HealthStatus]:
        checks = {
            "gateway": HealthStatus(
                name="gateway",
                status="ok",
                ready=not self.settings.allow_remote or bool(self.settings.api_token),
                details={
                    "bind": self.settings.host if self.settings.allow_remote else "127.0.0.1",
                    "port": self.settings.port,
                    "authentication": "bearer_token"
                    if self.settings.api_token
                    else "none_local_only",
                    "allowed_origins": list(self.settings.allowed_origins),
                },
            ),
            "workflows": self.workflows.health(),
            "hermes": self.hermes.health(),
            "codex": self.codex.health(),
            "permissions": self.permissions.health(),
            "privileged_helper": self.privileged.health(),
        }
        if self.memory is not None:
            checks["memory"] = self.memory.health()
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

    def authorize_http(
        self, method: str, path: str, headers: Mapping[str, str]
    ) -> tuple[int, dict[str, object]] | None:
        """Apply the M14 token, origin, and browser-write checks at the socket edge."""

        route = urlsplit(path).path
        if route in {"/", "/health", "/health/live", "/health/ready", "/api/v1/health"}:
            return None
        token = self.settings.api_token
        if self.settings.allow_remote and not token:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "success": False,
                "error": "remote_auth_not_configured",
            }
        if token:
            authorization = headers.get("Authorization", "")
            expected = f"Bearer {token}"
            if not hmac.compare_digest(authorization, expected):
                return HTTPStatus.UNAUTHORIZED, {
                    "success": False,
                    "error": "authentication_required",
                }
        origin = headers.get("Origin")
        if origin:
            if origin not in self.settings.allowed_origins:
                return HTTPStatus.FORBIDDEN, {
                    "success": False,
                    "error": "origin_not_allowed",
                }
            if method not in {"GET", "HEAD", "OPTIONS"} and (
                not token or not hmac.compare_digest(headers.get("X-Personal-AI-CSRF", ""), token)
            ):
                return HTTPStatus.FORBIDDEN, {
                    "success": False,
                    "error": "csrf_token_required",
                }
        return None

    def cors_origin(self, headers: Mapping[str, str]) -> str | None:
        origin = headers.get("Origin")
        return origin if origin in self.settings.allowed_origins else None

    def artifacts(
        self,
        *,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        catalog = ArtifactCatalog(self.settings.artifact_root, self.workflows)
        return [item.to_dict() for item in catalog.list(run_id=run_id, limit=limit, offset=offset)]

    def artifact_download(
        self,
        artifact_id: str,
        *,
        run_id: str | None = None,
    ) -> tuple[bytes, str, dict[str, object]]:
        catalog = ArtifactCatalog(self.settings.artifact_root, self.workflows)
        metadata = catalog.metadata(artifact_id, run_id=run_id)
        return (
            catalog.resolve(artifact_id, run_id=run_id).read_bytes(),
            metadata.content_type,
            metadata.to_dict(),
        )

    def event_stream(
        self,
        run_id: str,
        *,
        after_event_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> str:
        self.workflows.get(run_id)
        events = self.workflows.events(
            run_id,
            after_event_id=after_event_id,
            event_type=event_type,
            limit=limit,
        )
        chunks = []
        for event in events:
            chunks.append(
                "id: "
                + str(event.get("event_id", ""))
                + "\n"
                + "event: "
                + str(event.get("event_type", "message"))
                + "\n"
                + "data: "
                + json.dumps(event, ensure_ascii=False, sort_keys=True)
                + "\n\n"
            )
        return "".join(chunks)

    def tool_catalog(self) -> dict[str, Any]:
        return {
            "mode": "controlled-local-execution",
            "hermes": {
                "capabilities": ["hermes.chat", "hermes.codex_handoff"],
                "execution": "enabled_local_qwen_and_codex_boundary",
            },
            "codex": {
                "capabilities": ["codex.repository_handoff"],
                "execution": "enabled_if_cli_available",
            },
            "permissions": {
                "capabilities": ["approvals.request", "approvals.decide", "permissions.inspect"],
                "execution": "enabled_process_local",
            },
            "privileged_helper": {
                "capabilities": list(self.privileged.capabilities()),
                "execution": "disabled_fail_closed",
            },
            "providers": [
                {
                    "provider": provider.provider_name,
                    "capabilities": list(provider.capabilities()),
                    "execution": (
                        "enabled_controlled_allowlisted"
                        if provider.provider_name == "pc"
                        else "enabled_headless_and_fixture_boundary"
                        if provider.provider_name == "blender"
                        and provider.health().details.get("blender_available")
                        else "enabled_fixture_boundary_live_unavailable"
                        if provider.provider_name == "blender"
                        else "enabled_structured_project_boundary"
                        if provider.provider_name == "sc2"
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
        parsed = urlsplit(path)
        route = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=False)
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
        if route == "/api/v1/blender/invoke":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_provider("blender", body)
        if route == "/api/v1/sc2/invoke":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_provider("sc2", body)
        if route in {"/api/v1/blender/health", "/api/v1/sc2/health"}:
            if method != "GET":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            provider_name = route.split("/")[3]
            provider = next(
                (item for item in self.integrations if item.provider_name == provider_name), None
            )
            if provider is None:
                return HTTPStatus.NOT_FOUND, {
                    "error": "provider_not_found",
                    "provider": provider_name,
                }
            check = provider.health()
            return (
                HTTPStatus.OK if check.ready else HTTPStatus.SERVICE_UNAVAILABLE
            ), check.to_dict()
        if route == "/api/v1/approvals":
            if method == "POST":
                return self._dispatch_approval_create(body)
            if method == "GET":
                approvals = [item.to_dict() for item in self.permissions.list_requests()]
                approvals = _filter_records(
                    approvals,
                    status=_query_value(query, "status"),
                    field="status",
                    secondary=_query_value(query, "action"),
                    secondary_field="action",
                )
                return HTTPStatus.OK, _paged("approvals", approvals, query)
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
        if route == "/api/v1/approvals/events":
            if method != "GET":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            events = [item.to_dict() for item in self.permissions.events()]
            event_type = _query_value(query, "event_type")
            if event_type:
                events = [item for item in events if item.get("event_type") == event_type]
            return HTTPStatus.OK, _paged("events", events, query)
        if route.startswith("/api/v1/approvals/"):
            return self._dispatch_approval_route(method, route, body)
        if route == "/api/v1/privileged/invoke":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return self._dispatch_privileged(body)
        if route == "/api/v1/workflows":
            if method == "POST":
                return self._dispatch_workflow_start(body)
            if method != "GET":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            return HTTPStatus.OK, {"workflows": self.workflows.definitions()}
        if route == "/api/v1/artifacts" and method == "GET":
            catalog = ArtifactCatalog(self.settings.artifact_root, self.workflows)
            records = [
                item.to_dict()
                for item in catalog.list(run_id=_query_value(query, "run_id"), limit=10_000)
            ]
            return HTTPStatus.OK, _paged("artifacts", records, query)
        if route.startswith("/api/v1/artifacts/") and method == "GET":
            artifact_id = unquote(route.removeprefix("/api/v1/artifacts/"))
            try:
                catalog = ArtifactCatalog(self.settings.artifact_root, self.workflows)
                return HTTPStatus.OK, catalog.metadata(
                    artifact_id,
                    run_id=_query_value(query, "run_id"),
                ).to_dict()
            except (FileNotFoundError, PermissionError, ValueError) as exc:
                return HTTPStatus.NOT_FOUND, {"error": "artifact_not_found", "details": str(exc)}
        if route.startswith("/api/v1/runs/"):
            return self._dispatch_workflow_control(method, route, body, query)
        if route == "/api/v1/memory/semantic" and method == "POST":
            return self._dispatch_memory_semantic(body)
        if route == "/api/v1/memory/skills" and method == "POST":
            return self._dispatch_memory_skill(body)
        if route.startswith("/api/v1/memory/skills/"):
            return self._dispatch_memory_skill_control(method, route, body)
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
        if route == "/api/v1/permissions":
            return HTTPStatus.OK, self.permissions.policy.summary()
        if route == "/api/v1/privileged/health":
            return HTTPStatus.OK, self.privileged.health().to_dict()
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
            runs = self.workflows.list_runs(
                status=_query_value(query, "status"),
                workflow=_query_value(query, "workflow"),
            )
            return HTTPStatus.OK, _paged("runs", runs, query)
        if route == "/api/v1/memory/episodes" and method == "GET":
            if self.memory is None:
                return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
            limit, offset = _pagination_values(query)
            search = _query_value(query, "query")
            episodes = (
                self.memory.episodes.search(search, limit=10_000)
                if search
                else self.memory.episodes.list(limit=10_000)
            )
            success = _query_value(query, "success")
            if success in {"true", "false"}:
                episodes = [item for item in episodes if item.success == (success == "true")]
            records = [item.to_dict() for item in episodes]
            return HTTPStatus.OK, _paged("episodes", records, query, limit=limit, offset=offset)
        if route == "/api/v1/memory/semantic" and method == "GET":
            if self.memory is None:
                return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
            records = [item.to_dict() for item in self.memory.semantic.list()]
            key = _query_value(query, "key")
            if key:
                records = [item for item in records if item.get("key") == key]
            return HTTPStatus.OK, _paged("records", records, query)
        if route == "/api/v1/memory/skills" and method == "GET":
            if self.memory is None:
                return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
            skills = [item.to_dict() for item in self.memory.skills.list()]
            name = _query_value(query, "name")
            status = _query_value(query, "status")
            if name:
                skills = [item for item in skills if item.get("name") == name]
            if status:
                skills = [item for item in skills if item.get("status") == status]
            return HTTPStatus.OK, _paged("skills", skills, query)
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
            task, approval_id = coding_task_from_payload(self._decode_body(body))
        except (UnicodeDecodeError, json.JSONDecodeError, CodingTaskValidationError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }
        response = self.hermes.delegate_to_codex(task, approval_id=approval_id)
        if response.success:
            status = HTTPStatus.OK
        elif response.error in {"approval_required", "approval_requested"}:
            status = HTTPStatus.CONFLICT
        elif response.error and response.error.startswith("approval_"):
            status = HTTPStatus.FORBIDDEN
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
        status = self._tool_result_status(result.success, result.error)
        return status, result.to_dict()

    def _dispatch_provider(
        self,
        provider_name: str,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = self._mapping_body(body)
            action = self._required_string(payload, "action")
            target = payload.get("target")
            parameters = payload.get("parameters", {})
            if target is not None and not isinstance(target, str):
                raise ValueError("target must be a string when provided")
            if not isinstance(parameters, Mapping):
                raise ValueError("parameters must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }
        provider = next(
            (item for item in self.integrations if item.provider_name == provider_name), None
        )
        if provider is None:
            return HTTPStatus.NOT_FOUND, {"error": "provider_not_found", "provider": provider_name}
        result = provider.invoke(action, target=target, parameters=parameters)
        return self._tool_result_status(result.success, result.error), result.to_dict()

    def _dispatch_workflow_start(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = self._mapping_body(body)
            workflow = self._required_string(payload, "workflow")
            state = payload.get("state", {})
            task = payload.get("task", workflow)
            background = payload.get("background", True)
            if (
                not isinstance(state, Mapping)
                or not isinstance(task, str)
                or not isinstance(background, bool)
            ):
                raise ValueError("task must be a string, state an object, and background a boolean")
            run = self.workflows.start(workflow, task=task, state=state, background=background)
            return HTTPStatus.ACCEPTED if background else HTTPStatus.OK, run.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }

    def _dispatch_workflow_control(
        self,
        method: str,
        route: str,
        body: bytes | Mapping[str, object] | None,
        query: Mapping[str, list[str]] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        query = query or {}
        parts = route.removeprefix("/api/v1/runs/").split("/")
        if len(parts) == 1 and method == "GET":
            try:
                return HTTPStatus.OK, self.workflows.get(parts[0]).to_dict()
            except KeyError as exc:
                return HTTPStatus.NOT_FOUND, {"error": "run_not_found", "details": str(exc)}
        if len(parts) == 2 and parts[1] == "events" and method == "GET":
            try:
                self.workflows.get(parts[0])
            except KeyError as exc:
                return HTTPStatus.NOT_FOUND, {"error": "run_not_found", "details": str(exc)}
            limit, _ = _pagination_values(query)
            events = self.workflows.events(
                parts[0],
                after_event_id=_query_value(query, "after"),
                event_type=_query_value(query, "event_type"),
                limit=limit,
            )
            return HTTPStatus.OK, {
                "events": events,
                "pagination": {"limit": limit, "count": len(events)},
            }
        if (
            len(parts) != 2
            or method != "POST"
            or parts[1] not in {"pause", "resume", "cancel", "retry", "steer"}
        ):
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
        try:
            if parts[1] == "pause":
                run = self.workflows.pause(parts[0])
            elif parts[1] == "resume":
                payload = self._mapping_body(body, allow_none=True)
                state = payload.get("state", {})
                if not isinstance(state, Mapping):
                    raise ValueError("resume state must be an object")
                run = self.workflows.resume(parts[0], state=state)
            elif parts[1] == "cancel":
                run = self.workflows.cancel(parts[0])
            elif parts[1] == "retry":
                run = self.workflows.retry(parts[0])
            else:
                payload = self._mapping_body(body)
                instruction = self._required_string(payload, "instruction")
                run = self.workflows.steer(parts[0], instruction)
            return HTTPStatus.OK, run.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            return HTTPStatus.CONFLICT if isinstance(exc, ValueError) else HTTPStatus.NOT_FOUND, {
                "success": False,
                "error": "workflow_control_failed",
                "details": str(exc),
            }

    def _dispatch_memory_semantic(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        if self.memory is None:
            return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
        try:
            payload = self._mapping_body(body)
            key = self._required_string(payload, "key")
            if "value" not in payload:
                raise ValueError("value is required")
            source = self._required_string(payload, "source")
            record = self.memory.semantic.remember(key, payload["value"], source=source)
            return HTTPStatus.CREATED, record.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }

    def _dispatch_memory_skill(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        if self.memory is None:
            return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
        try:
            payload = self._mapping_body(body)
            name = self._required_string(payload, "name")
            steps = payload.get("steps")
            episodes = payload.get("source_episode_ids", [])
            if not isinstance(steps, list) or not isinstance(episodes, list):
                raise ValueError("steps and source_episode_ids must be arrays")
            known_episode_ids = {
                episode.episode_id for episode in self.memory.episodes.list(limit=10_000)
            }
            if any(not isinstance(item, str) or item not in known_episode_ids for item in episodes):
                raise ValueError("source_episode_ids must reference recorded episodes")
            skill = self.memory.skills.create_candidate(
                name=name,
                steps=steps,
                source_episode_ids=episodes,
            )
            return HTTPStatus.CREATED, skill.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }

    def _dispatch_memory_skill_control(
        self,
        method: str,
        route: str,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        if self.memory is None:
            return HTTPStatus.NOT_FOUND, {"error": "memory_not_configured"}
        parts = route.removeprefix("/api/v1/memory/skills/").split("/")
        if len(parts) != 2 or method != "POST" or parts[1] not in {"validate", "promote"}:
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
        try:
            if parts[1] == "promote":
                skill = self.memory.skills.promote(parts[0])
            else:
                payload = self._mapping_body(body)
                success = payload.get("success")
                if not isinstance(success, bool):
                    raise ValueError("success must be a boolean")
                notes = payload.get("notes", "")
                if not isinstance(notes, str):
                    raise ValueError("notes must be a string")
                skill = self.memory.skills.validate(parts[0], success=success, notes=notes)
            return HTTPStatus.OK, skill.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            return HTTPStatus.CONFLICT, {
                "success": False,
                "error": "skill_operation_failed",
                "details": str(exc),
            }

    def _dispatch_approval_create(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = self._mapping_body(body)
            action = self._required_string(payload, "action")
            target = payload.get("target")
            parameters = payload.get("parameters", {})
            reason = payload.get("reason", "Action requires explicit approval.")
            requested_by = payload.get("requested_by", "gateway")
            if target is not None and not isinstance(target, str):
                raise ValueError("target must be a string when provided")
            if not isinstance(parameters, Mapping):
                raise ValueError("parameters must be a JSON object")
            if not isinstance(reason, str) or not isinstance(requested_by, str):
                raise ValueError("reason and requested_by must be strings")
            request = self.permissions.request_approval(
                action,
                target=target,
                parameters=parameters,
                reason=reason,
                requested_by=requested_by,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            PermissionServiceError,
            ValueError,
        ) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": getattr(exc, "code", "invalid_request"),
                "details": str(exc),
            }
        return HTTPStatus.CREATED, request.to_dict()

    def _dispatch_approval_route(
        self,
        method: str,
        route: str,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        parts = route.removeprefix("/api/v1/approvals/").split("/")
        approval_id = parts[0]
        try:
            if len(parts) == 1 and method == "GET":
                return HTTPStatus.OK, self.permissions.get(approval_id).to_dict()
            if (
                len(parts) != 2
                or method != "POST"
                or parts[1]
                not in {
                    "accept",
                    "reject",
                    "cancel",
                }
            ):
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
            payload = self._mapping_body(body, allow_none=True)
            decided_by = payload.get("decided_by", "user")
            reason = payload.get("reason")
            if not isinstance(decided_by, str) or (
                reason is not None and not isinstance(reason, str)
            ):
                raise ValueError("decided_by and reason must be strings")
            status = {"accept": "accepted", "reject": "rejected", "cancel": "cancelled"}[parts[1]]
            request = self.permissions.decide(
                approval_id,
                status,
                decided_by=decided_by,
                reason=reason,
            )
            return HTTPStatus.OK, request.to_dict()
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            PermissionServiceError,
            ValueError,
        ) as exc:
            code = getattr(exc, "code", "invalid_request")
            http_status = (
                HTTPStatus.NOT_FOUND if code == "approval_not_found" else HTTPStatus.CONFLICT
            )
            return http_status, {"success": False, "error": code, "details": str(exc)}

    def _dispatch_privileged(
        self,
        body: bytes | Mapping[str, object] | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = self._mapping_body(body)
            action = self._required_string(payload, "action")
            target = payload.get("target")
            parameters = payload.get("parameters", {})
            if target is not None and not isinstance(target, str):
                raise ValueError("target must be a string when provided")
            if not isinstance(parameters, Mapping):
                raise ValueError("parameters must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "success": False,
                "error": "invalid_request",
                "details": str(exc),
            }
        result = self.privileged.invoke(action, target=target, parameters=parameters)
        return self._tool_result_status(result.success, result.error), result.to_dict()

    @staticmethod
    def _tool_result_status(success: bool, error: str | None) -> HTTPStatus:
        if success:
            return HTTPStatus.OK
        if error == "approval_required":
            return HTTPStatus.CONFLICT
        if error and (error.startswith("approval_") or error.startswith("privileged_")):
            return HTTPStatus.FORBIDDEN
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def _mapping_body(
        self,
        body: bytes | Mapping[str, object] | None,
        *,
        allow_none: bool = False,
    ) -> Mapping[str, object]:
        payload = self._decode_body(body)
        if payload is None and allow_none:
            return {}
        if not isinstance(payload, Mapping):
            raise ValueError("request body must be a JSON object")
        return payload

    @staticmethod
    def _required_string(payload: Mapping[str, object], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _decode_body(body: bytes | Mapping[str, object] | None) -> object:
        if isinstance(body, (bytes, bytearray)):
            return json.loads(body.decode("utf-8"))
        return body


def _query_value(query: Mapping[str, list[str]], name: str) -> str | None:
    values = query.get(name, [])
    return values[0] if values else None


def _pagination_values(query: Mapping[str, list[str]]) -> tuple[int, int]:
    try:
        limit = int(_query_value(query, "limit") or "50")
        offset = int(_query_value(query, "offset") or "0")
    except ValueError:
        return 50, 0
    return min(max(limit, 1), 100), max(offset, 0)


def _paged(
    key: str,
    records: list[dict[str, object]],
    query: Mapping[str, list[str]],
    *,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, object]:
    if limit is None or offset is None:
        limit, offset = _pagination_values(query)
    items = records[offset : offset + limit]
    return {
        key: items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "total": len(records),
            "has_more": offset + len(items) < len(records),
        },
    }


def _filter_records(
    records: list[dict[str, object]],
    *,
    status: str | None,
    field: str,
    secondary: str | None,
    secondary_field: str,
) -> list[dict[str, object]]:
    if status:
        records = [record for record in records if record.get(field) == status]
    if secondary:
        records = [record for record in records if record.get(secondary_field) == secondary]
    return records


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter kept separate so dispatch can be tested without sockets."""

    app: GatewayApp

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._handle("POST")

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        origin = self.headers.get("Origin")
        if origin and origin in self.app.settings.allowed_origins:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header(
                "Access-Control-Allow-Headers", "Authorization, Content-Type, X-Personal-AI-CSRF"
            )
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
            self.end_headers()
            return
        self.send_error(HTTPStatus.FORBIDDEN, "origin_not_allowed")

    def _handle(self, method: str) -> None:
        headers = {key: value for key, value in self.headers.items()}
        denied = self.app.authorize_http(method, self.path, headers)
        if denied is not None:
            self._send_json(denied[0], denied[1], headers)
            return
        route = urlsplit(self.path).path
        if route.startswith("/api/v1/artifacts/") and method == "GET":
            artifact_id = unquote(route.removeprefix("/api/v1/artifacts/"))
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=False)
            try:
                payload, content_type, metadata = self.app.artifact_download(
                    artifact_id,
                    run_id=_query_value(query, "run_id"),
                )
            except FileNotFoundError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "artifact_not_found"}, headers)
                return
            except (PermissionError, ValueError) as exc:
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "artifact_access_denied", "details": str(exc)},
                    headers,
                )
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", f'attachment; filename="{metadata["name"]}"')
            self._send_cors(headers)
            self.end_headers()
            self.wfile.write(payload)
            return
        if (
            route.startswith("/api/v1/runs/")
            and route.endswith("/events/stream")
            and method == "GET"
        ):
            parts = route.removeprefix("/api/v1/runs/").removesuffix("/events/stream")
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=False)
            try:
                body = self.app.event_stream(
                    parts.rstrip("/"),
                    after_event_id=_query_value(query, "after")
                    or self.headers.get("Last-Event-ID"),
                    event_type=_query_value(query, "event_type"),
                    limit=_pagination_values(query)[0],
                ).encode("utf-8")
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "run_not_found"}, headers)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors(headers)
            self.end_headers()
            self.wfile.write(body)
            return
        body = None
        if method == "POST":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            body = self.rfile.read(content_length)
        status, payload = self.app.dispatch(method, self.path, body)
        self._send_json(status, payload, headers)

    def _send_json(
        self, status: int, payload: Mapping[str, object], headers: Mapping[str, str]
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors(headers)
        self.end_headers()
        self.wfile.write(body)

    def _send_cors(self, headers: Mapping[str, str]) -> None:
        origin = self.app.cors_origin(headers)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def log_message(self, format_string: str, *args: object) -> None:
        logger.info("http_request", extra={"http": format_string % args})


def serve(app: GatewayApp) -> None:
    """Run the local gateway until interrupted."""

    if app.settings.allow_remote and not app.settings.api_token:
        raise RuntimeError("PERSONAL_AI_API_TOKEN is required before remote binding is enabled")
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
