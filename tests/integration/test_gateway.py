from http import HTTPStatus

from services.gateway.app import GatewayApp


def test_gateway_health_reports_all_m0_components() -> None:
    status, payload = GatewayApp.create_default().dispatch("GET", "/health")

    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert set(payload["checks"]) == {"gateway", "workflows", "pc", "blender", "sc2"}
    assert all(check["ready"] for check in payload["checks"].values())


def test_gateway_exposes_discovery_without_tool_execution() -> None:
    status, payload = GatewayApp.create_default().dispatch("GET", "/api/v1/tools")

    assert status == HTTPStatus.OK
    assert payload["mode"] == "discovery-only"
    assert all(provider["execution"] == "disabled_in_m0" for provider in payload["providers"])


def test_gateway_rejects_mutating_http_methods_in_m0() -> None:
    status, payload = GatewayApp.create_default().dispatch("POST", "/api/v1/tools")

    assert status == HTTPStatus.METHOD_NOT_ALLOWED
    assert payload == {"error": "method_not_allowed"}
