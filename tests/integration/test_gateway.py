import json
import subprocess
import sys
from http import HTTPStatus

from integrations.pc.service import PcIntegration
from personal_ai.config import Settings
from personal_ai.hermes import HermesService
from personal_ai.router import ModelRouter
from services.codex.service import CodexHandoffService
from services.gateway.app import GatewayApp
from services.privileged_helper.service import PrivilegedHelperService
from services.workflows.service import WorkflowService
from tests.support import FakeCodexBackend, FakePcBackend, FakeQwenClient, make_permission_service


def make_test_app() -> GatewayApp:
    client = FakeQwenClient()
    permissions = make_permission_service()
    codex = CodexHandoffService(FakeCodexBackend(), permissions)
    pc = PcIntegration(permissions, backend=FakePcBackend())
    defaults = GatewayApp.create_default(model_client=client)
    return GatewayApp(
        settings=Settings(),
        workflows=WorkflowService(),
        integrations=(pc, defaults.integrations[1], defaults.integrations[2]),
        hermes=HermesService(client, ModelRouter()),
        codex=codex,
        pc=pc,
        permissions=permissions,
        privileged=PrivilegedHelperService.create_disabled(permissions),
    )


def test_gateway_health_reports_all_m0_components() -> None:
    status, payload = make_test_app().dispatch("GET", "/health")

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert set(payload["checks"]) == {
        "gateway",
        "workflows",
        "hermes",
        "codex",
        "permissions",
        "privileged_helper",
        "pc",
        "blender",
        "sc2",
    }
    assert all(check["ready"] for check in payload["checks"].values())


def test_gateway_exposes_discovery_without_tool_execution() -> None:
    status, payload = make_test_app().dispatch("GET", "/api/v1/tools")

    assert status == HTTPStatus.OK
    assert payload["mode"] == "controlled-local-execution"
    assert payload["hermes"]["execution"] == "enabled_local_qwen"
    assert payload["codex"]["execution"] == "enabled_if_cli_available"
    assert payload["providers"][0]["execution"] == "enabled_controlled_allowlisted"
    assert all(
        provider["execution"] == "disabled_until_future_milestone"
        for provider in payload["providers"][1:]
    )


def test_gateway_chat_returns_hermes_response() -> None:
    app = make_test_app()
    status, payload = app.dispatch(
        "POST",
        "/api/v1/chat",
        json.dumps({"message": "Hello", "conversation_id": "test-conversation"}).encode(),
    )

    assert status == HTTPStatus.OK
    assert payload["success"] is True
    assert payload["conversation_id"] == "test-conversation"
    assert payload["message"]["role"] == "assistant"
    assert payload["model"] == "qwen-local"


def test_gateway_chat_rejects_invalid_payload() -> None:
    status, payload = make_test_app().dispatch("POST", "/api/v1/chat", b"not-json")

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["success"] is False
    assert payload["error"] == "invalid_request"


def test_gateway_chat_returns_structured_unavailable_qwen_error() -> None:
    settings = Settings(
        qwen_base_url="http://127.0.0.1:1/v1",
        qwen_health_timeout_seconds=0.1,
        qwen_timeout_seconds=0.1,
    )
    app = GatewayApp.create_default(settings)
    status, payload = app.dispatch(
        "POST",
        "/api/v1/chat",
        json.dumps({"message": "Hello"}).encode(),
    )

    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert payload["success"] is False
    assert payload["error"] == "qwen_unavailable"
    assert payload["warnings"] == ["Start or check the configured local Qwen server."]


def test_gateway_rejects_mutating_http_methods_in_m0() -> None:
    status, payload = make_test_app().dispatch("POST", "/api/v1/tools")

    assert status == HTTPStatus.METHOD_NOT_ALLOWED
    assert payload == {"error": "method_not_allowed"}


def test_gateway_pc_route_requires_approval_for_mutation() -> None:
    app = make_test_app()
    status, payload = app.dispatch(
        "POST",
        "/api/v1/pc/invoke",
        {"action": "pc.input.type", "parameters": {"text": "blocked"}},
    )

    assert status == HTTPStatus.CONFLICT
    assert payload["error"] == "approval_required"
    assert payload["approval_level"] == 2


def test_gateway_pc_route_returns_structured_success() -> None:
    app = make_test_app()
    status, payload = app.dispatch(
        "POST",
        "/api/v1/pc/invoke",
        {
            "action": "pc.system_info",
            "parameters": {},
        },
    )

    assert status == HTTPStatus.OK
    assert payload["success"] is True
    assert payload["tool"] == "pc.system_info"
    assert payload["data"]["action"] == "pc.system_info"


def test_gateway_codex_route_returns_observable_handoff(tmp_path) -> None:
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    app = make_test_app()

    request = {
        "task_id": "gateway-handoff",
        "repository_path": str(repo),
        "task": "write the fixture marker",
        "test_command": [
            sys.executable,
            "-c",
            "from pathlib import Path; assert Path('codex-handoff.txt').exists()",
        ],
    }
    pending_status, pending = app.dispatch(
        "POST",
        "/api/v1/codex/handoff",
        request,
    )
    assert pending_status == HTTPStatus.CONFLICT
    approval_id = pending["approval"]["approval_id"]
    decision_status, decision = app.dispatch(
        "POST",
        f"/api/v1/approvals/{approval_id}/accept",
        {"reason": "integration test"},
    )
    assert decision_status == HTTPStatus.OK
    assert decision["status"] == "accepted"

    request["approval_id"] = approval_id
    status, payload = app.dispatch("POST", "/api/v1/codex/handoff", request)

    assert status == HTTPStatus.OK
    assert payload["success"] is True
    assert payload["task_id"] == "gateway-handoff"
    assert payload["changed_files"] == ["codex-handoff.txt"]
    assert payload["tests"][0]["success"] is True


def test_gateway_exposes_approval_lifecycle_and_audit_events() -> None:
    app = make_test_app()
    status, pending = app.dispatch(
        "POST",
        "/api/v1/approvals",
        {
            "action": "pc.input.type",
            "parameters": {"text": "approved"},
            "reason": "integration test",
            "requested_by": "test-user",
        },
    )
    assert status == HTTPStatus.CREATED
    approval_id = pending["approval_id"]

    status, accepted = app.dispatch(
        "POST",
        f"/api/v1/approvals/{approval_id}/accept",
        {"decided_by": "test-user"},
    )
    assert status == HTTPStatus.OK
    assert accepted["status"] == "accepted"

    status, result = app.dispatch(
        "POST",
        "/api/v1/pc/invoke",
        {
            "action": "pc.input.type",
            "parameters": {"text": "approved", "approval_id": approval_id},
        },
    )
    assert status == HTTPStatus.OK
    assert result["data"]["permission"]["automatic"] is False

    status, events = app.dispatch("GET", "/api/v1/approvals/events")
    assert status == HTTPStatus.OK
    assert {event["event_type"] for event in events["events"]} >= {
        "approval.requested",
        "approval.accepted",
        "approval.consumed",
    }


def test_gateway_privileged_action_fails_closed_after_approval() -> None:
    app = make_test_app()
    status, pending = app.dispatch(
        "POST",
        "/api/v1/privileged/invoke",
        {"action": "privileged.system.execute", "parameters": {"operation": "fixture"}},
    )
    assert status == HTTPStatus.CONFLICT
    approval_id = pending["data"]["permission"]["approval"]["approval_id"]
    app.dispatch("POST", f"/api/v1/approvals/{approval_id}/accept", {})

    status, result = app.dispatch(
        "POST",
        "/api/v1/privileged/invoke",
        {
            "action": "privileged.system.execute",
            "parameters": {"operation": "fixture", "approval_id": approval_id},
        },
    )

    assert status == HTTPStatus.FORBIDDEN
    assert result["error"] == "privileged_helper_unavailable"
