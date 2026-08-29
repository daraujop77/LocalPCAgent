import pytest

from services.gateway.artifacts import ArtifactCatalog
from services.workflows.service import WorkflowService


def test_artifact_catalog_reports_metadata_and_blocks_escape(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    artifact = artifact_root / "preview.png"
    artifact.write_bytes(b"png")
    catalog = ArtifactCatalog(artifact_root, WorkflowService(tmp_path / "runs"))

    records = catalog.list()

    assert records[0].artifact_id == "preview.png"
    assert records[0].content_type == "image/png"
    assert records[0].size == 3
    with pytest.raises(ValueError):
        catalog.resolve("../secret.txt")


def test_artifact_catalog_hides_workflow_storage(tmp_path) -> None:
    artifact_root = tmp_path / "artifacts"
    internal = artifact_root / "workflows"
    internal.mkdir(parents=True)
    (internal / "runs.json").write_text("[]", encoding="utf-8")
    catalog = ArtifactCatalog(artifact_root, WorkflowService(tmp_path / "runs"))

    assert catalog.list() == []
    with pytest.raises(PermissionError):
        catalog.resolve("workflows/runs.json")
