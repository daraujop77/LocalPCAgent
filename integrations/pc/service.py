"""Safe PC integration skeleton. No unrestricted PC control is implemented."""

from personal_ai.integration import SkeletonIntegration


class PcIntegration(SkeletonIntegration):
    provider_name = "pc"
    _capabilities = (
        "pc.system_info",
        "pc.list_processes",
        "pc.apps.launch",
        "pc.files.read",
        "pc.shell.powershell",
        "pc.screen.capture",
    )
