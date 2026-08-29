from integrations.blender.service import BlenderIntegration
from integrations.pc.service import PcIntegration
from integrations.sc2.service import Sc2Integration
from tests.support import make_permission_service


def test_pc_is_controlled_while_future_integrations_remain_disabled() -> None:
    providers = (PcIntegration(make_permission_service()), BlenderIntegration(), Sc2Integration())

    assert {provider.provider_name for provider in providers} == {"pc", "blender", "sc2"}
    assert providers[0].health().details["control_enabled"] is True
    assert providers[1].health().details["control_enabled"] is False
    assert providers[2].health().details["control_enabled"] is False

    result = providers[0].invoke("pc.shell.powershell")
    assert result.success is False
    assert result.error == "approval_required"
    assert result.approval_level == 2

    future_result = providers[1].invoke("blender.execute_bpy")
    assert future_result.success is False
    assert future_result.error == "not_implemented"
