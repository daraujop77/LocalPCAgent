"""Safe artifact metadata and download boundary for the local gateway."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    artifact_id: str
    path: str
    name: str
    content_type: str
    size: int
    run_id: str | None
    workflow: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "name": self.name,
            "content_type": self.content_type,
            "size": self.size,
            "provenance": {"run_id": self.run_id, "workflow": self.workflow},
        }


class ArtifactCatalog:
    """Enumerate only files below the configured artifact root."""

    def __init__(self, root: str | Path, workflow_service: Any) -> None:
        configured = Path(root).expanduser()
        self.root = (
            Path.cwd() / configured if not configured.is_absolute() else configured
        ).resolve()
        self.workflow_service = workflow_service

    def list(
        self,
        *,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArtifactMetadata]:
        provenance = self._provenance(run_id)
        paths: dict[str, Path] = {}
        if run_id is None:
            for path in self.root.rglob("*") if self.root.exists() else ():
                if path.is_file() and self._is_public_path(path):
                    paths[path.relative_to(self.root).as_posix()] = path
        for stored_path, details in provenance.items():
            resolved = self._resolve_stored_path(stored_path)
            if resolved is not None and resolved.is_file() and self._is_public_path(resolved):
                paths[resolved.relative_to(self.root).as_posix()] = resolved
        records = [
            self._metadata(relative, path, provenance.get(self._workspace_relative(path)))
            for relative, path in sorted(paths.items())
        ]
        return records[max(0, offset) : max(0, offset) + max(0, limit)]

    def resolve(self, artifact_id: str, *, run_id: str | None = None) -> Path:
        relative = unquote(artifact_id).replace("\\", "/")
        candidate = (self.root / relative).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact path must remain inside the artifact root") from exc
        if not candidate.is_file():
            raise FileNotFoundError(relative)
        if not self._is_public_path(candidate):
            raise PermissionError("internal workflow storage is not a downloadable artifact")
        if run_id is not None:
            allowed = {metadata.artifact_id for metadata in self.list(run_id=run_id, limit=10_000)}
            if relative not in allowed:
                raise PermissionError("artifact is not associated with the requested run")
        return candidate

    def _is_public_path(self, path: Path) -> bool:
        try:
            path.relative_to(self.root / "workflows")
        except ValueError:
            return True
        return False

    def metadata(self, artifact_id: str, *, run_id: str | None = None) -> ArtifactMetadata:
        path = self.resolve(artifact_id, run_id=run_id)
        provenance = self._provenance(run_id)
        return self._metadata(
            path.relative_to(self.root).as_posix(),
            path,
            provenance.get(self._workspace_relative(path)),
        )

    def _provenance(self, run_id: str | None) -> dict[str, dict[str, str | None]]:
        result: dict[str, dict[str, str | None]] = {}
        for run in self.workflow_service.list_runs():
            if run_id is not None and run.get("run_id") != run_id:
                continue
            current_run = run.get("run_id")
            workflow = run.get("workflow")
            for stored_path in run.get("artifacts", []):
                if isinstance(stored_path, str):
                    result[stored_path] = {
                        "run_id": str(current_run) if current_run else None,
                        "workflow": str(workflow) if workflow else None,
                    }
        return result

    def _resolve_stored_path(self, stored_path: str) -> Path | None:
        candidate = Path(stored_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate

    def _workspace_relative(self, path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _metadata(
        relative: str,
        path: Path,
        provenance: dict[str, str | None] | None,
    ) -> ArtifactMetadata:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return ArtifactMetadata(
            artifact_id=relative,
            path=relative,
            name=path.name,
            content_type=content_type,
            size=path.stat().st_size,
            run_id=provenance.get("run_id") if provenance else None,
            workflow=provenance.get("workflow") if provenance else None,
        )
