from integrations.sc2.service import LocalSc2Backend, Sc2Execution, Sc2Integration
from personal_ai.contracts import HealthStatus
from tests.support import make_permission_service


class FakeSc2Backend:
    def __init__(self) -> None:
        self.calls = []

    def health(self) -> HealthStatus:
        return HealthStatus("sc2", "ok", True, {"backend": "fake"})

    def execute(self, action, *, target, parameters):
        self.calls.append((action, target, parameters))
        return Sc2Execution(True, "fake SC2 operation completed")


def test_sc2_project_inspection_search_validation_and_patch(tmp_path) -> None:
    project = tmp_path / "mod"
    project.mkdir()
    (project / "Units.xml").write_text(
        '<Catalog><Unit id="Marine"><LifeMax value="45" /></Unit></Catalog>',
        encoding="utf-8",
    )
    (project / "Map.galaxy").write_text('include "Base"\nvoid main() {}\n', encoding="utf-8")
    backend = LocalSc2Backend(workspace_root=tmp_path, artifact_root="artifacts")

    inspected = backend.execute("sc2.project.inspect", target="mod", parameters={})
    found = backend.execute("sc2.search", target="mod", parameters={"query": "Marine"})
    valid = backend.execute("sc2.galaxy.validate", target="mod", parameters={})
    patched = backend.execute(
        "sc2.galaxy.patch",
        target="mod",
        parameters={"file": "Units.xml", "search": "45", "replace": "50"},
    )

    assert inspected.success is True
    assert found.data["matches"]
    assert valid.success is True
    assert patched.success is True
    assert "50" in (project / "Units.xml").read_text(encoding="utf-8")


def test_sc2_mutation_is_centrally_approval_gated() -> None:
    fake = FakeSc2Backend()
    integration = Sc2Integration(make_permission_service(), backend=fake)

    pending = integration.invoke(
        "sc2.galaxy.patch",
        target="mod",
        parameters={"file": "Map.galaxy", "search": "old", "replace": "new"},
    )

    assert pending.success is False
    assert pending.error == "approval_required"
    assert fake.calls == []
