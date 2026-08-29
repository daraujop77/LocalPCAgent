"""SC2 integration skeleton. Structured project tooling is deferred to M8+."""

from personal_ai.integration import SkeletonIntegration


class Sc2Integration(SkeletonIntegration):
    provider_name = "sc2"
    _capabilities = (
        "sc2.project.inspect",
        "sc2.project.snapshot",
        "sc2.search",
        "sc2.galaxy.validate",
    )
