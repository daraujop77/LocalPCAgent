import json

from integrations.blender.service import (
    BlenderExecution,
    BlenderIntegration,
    LocalBlenderBackend,
)
from personal_ai.contracts import HealthStatus
from personal_ai.memory import MemoryService
from services.workflows.definitions import blender_workflow
from services.workflows.service import WorkflowService
from tests.support import make_permission_service


class FakeBlenderBackend:
    def __init__(self) -> None:
        self.calls = []

    def health(self) -> HealthStatus:
        return HealthStatus("blender", "ok", True, {"backend": "fake", "control_enabled": True})

    def execute(self, action, *, target, parameters):
        self.calls.append((action, target, parameters))
        return BlenderExecution(True, "fake Blender operation completed", data={"fixture": True})


def test_blender_fixture_inspection_and_copy_preserve_source(tmp_path) -> None:
    source = tmp_path / "scene.json"
    source.write_text(json.dumps({"objects": [{"name": "Cube", "type": "MESH"}]}), encoding="utf-8")
    backend = LocalBlenderBackend(
        workspace_root=tmp_path, artifact_root="artifacts", executable="missing-blender"
    )

    inspected = backend.execute("blender.inspect_scene", target="scene.json", parameters={})
    copied = backend.execute("blender.save_copy", target="scene.json", parameters={})

    assert inspected.success is True
    assert inspected.data["scene"]["objects"][0]["name"] == "Cube"
    assert copied.success is True
    assert copied.artifacts
    assert source.read_text(encoding="utf-8") == json.dumps(
        {"objects": [{"name": "Cube", "type": "MESH"}]}
    )


def test_blender_mutation_is_centrally_approval_gated() -> None:
    fake = FakeBlenderBackend()
    integration = BlenderIntegration(make_permission_service(), backend=fake)

    pending = integration.invoke(
        "blender.execute_bpy", target="working.blend", parameters={"operations": []}
    )

    assert pending.success is False
    assert pending.error == "approval_required"
    assert fake.calls == []


def test_blender_fixture_workflow_completes_without_gui_or_blender(tmp_path) -> None:
    source = tmp_path / "scene.json"
    source.write_text(json.dumps({"objects": [{"name": "Cube"}]}), encoding="utf-8")
    permissions = make_permission_service()
    backend = LocalBlenderBackend(
        workspace_root=tmp_path, artifact_root="artifacts", executable="missing"
    )
    provider = BlenderIntegration(permissions, backend=backend)
    memory = MemoryService(tmp_path / "memory")
    service = WorkflowService(tmp_path / "runs", memory=memory)

    run = service.start(
        blender_workflow(provider, memory),
        state={
            "source": "scene.json",
            "task": "fixture workflow",
            "allow_inspection_only": True,
        },
        background=False,
    )

    assert run.status == "completed"
    assert run.state["validated"] is True
    assert any(path.endswith("-preview.png") for path in run.artifacts)
    assert memory.episodes.list()[0].success is True


def test_blender_workflow_rejects_unplanned_empty_mutation(tmp_path) -> None:
    source = tmp_path / "scene.json"
    source.write_text(json.dumps({"objects": []}), encoding="utf-8")
    permissions = make_permission_service()
    provider = BlenderIntegration(
        permissions,
        backend=LocalBlenderBackend(
            workspace_root=tmp_path,
            artifact_root="artifacts",
            executable="missing",
        ),
    )
    memory = MemoryService(tmp_path / "memory")
    run = WorkflowService(tmp_path / "runs", memory=memory).start(
        blender_workflow(provider, memory),
        state={"source": "scene.json", "task": "must modify"},
        background=False,
    )

    assert run.status == "failed"
    assert "requires explicit operations" in run.errors[0]


def test_blender_bpy_rejects_original_blend_target(tmp_path) -> None:
    source = tmp_path / "scene.blend"
    source.write_bytes(b"fixture")
    backend = LocalBlenderBackend(
        workspace_root=tmp_path,
        artifact_root="artifacts",
        executable="missing-blender",
    )

    result = backend.execute(
        "blender.execute_bpy",
        target="scene.blend",
        parameters={"operations": [{"op": "set_render_engine", "value": "BLENDER_WORKBENCH"}]},
    )

    assert result.success is False
    assert result.error == "blender_request_invalid"
    assert source.read_bytes() == b"fixture"
