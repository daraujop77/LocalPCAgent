from integrations.blender.service import BlenderIntegration
from integrations.pc.service import PcIntegration
from integrations.sc2.service import Sc2Integration


def test_integration_skeletons_are_ready_but_do_not_control_hosts() -> None:
    providers = (PcIntegration(), BlenderIntegration(), Sc2Integration())

    assert {provider.provider_name for provider in providers} == {"pc", "blender", "sc2"}
    assert all(provider.health().ready for provider in providers)
    assert all(provider.health().details["control_enabled"] is False for provider in providers)

    result = providers[0].invoke("pc.shell.powershell")
    assert result.success is False
    assert result.error == "not_implemented"
    assert result.approval_level == 0
