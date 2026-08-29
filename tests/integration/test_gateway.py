import json
from http import HTTPStatus

from personal_ai.config import Settings
from personal_ai.hermes import HermesService
from personal_ai.router import ModelRouter
from services.gateway.app import GatewayApp
from services.workflows.service import WorkflowService
from tests.support import FakeQwenClient


def make_test_app() -> GatewayApp:
    client = FakeQwenClient()
    return GatewayApp(
        settings=Settings(),
        workflows=WorkflowService(),
        integrations=GatewayApp.create_default(model_client=client).integrations,
        hermes=HermesService(client, ModelRouter()),
    )


def test_gateway_health_reports_all_m0_components() -> None:
    status, payload = make_test_app().dispatch("GET", "/health")

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert set(payload["checks"]) == {"gateway", "workflows", "hermes", "pc", "blender", "sc2"}
    assert all(check["ready"] for check in payload["checks"].values())


def test_gateway_exposes_discovery_without_tool_execution() -> None:
    status, payload = make_test_app().dispatch("GET", "/api/v1/tools")

    assert status == HTTPStatus.OK
    assert payload["mode"] == "discovery-and-chat"
    assert payload["hermes"]["execution"] == "enabled_local_qwen"
    assert all(provider["execution"] == "disabled_in_m1" for provider in payload["providers"])


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
