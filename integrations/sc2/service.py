"""Structured, local-first StarCraft II project integration.

The backend operates on project directories and ZIP-compatible working
copies. It does not launch Galaxy Editor or the game automatically; those
operations remain explicit capability boundaries until a validated local tool
is configured.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4
from xml.etree import ElementTree

from personal_ai.contracts import HealthStatus, ToolResult
from personal_ai.integration import SkeletonIntegration
from personal_ai.permissions import PermissionDecision, PermissionService

logger = logging.getLogger(__name__)

SC2_ACTIONS = (
    "sc2.project.inspect",
    "sc2.project.snapshot",
    "sc2.project.unpack",
    "sc2.project.pack",
    "sc2.search",
    "sc2.unit.read",
    "sc2.unit.modify",
    "sc2.weapon.read",
    "sc2.weapon.modify",
    "sc2.effect.read",
    "sc2.effect.modify",
    "sc2.upgrade.read",
    "sc2.upgrade.modify",
    "sc2.actor.read",
    "sc2.actor.modify",
    "sc2.trigger.inspect",
    "sc2.trigger.modify",
    "sc2.galaxy.read",
    "sc2.galaxy.patch",
    "sc2.galaxy.validate",
    "sc2.editor.launch",
    "sc2.map.test",
    "sc2.test.collect_logs",
    "sc2.package",
)


@dataclass(frozen=True, slots=True)
class Sc2Execution:
    success: bool
    summary: str
    changed_files: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    data: Mapping[str, object] | None = None
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None
    reversible: bool = True
    duration_ms: int | None = None


class Sc2Backend(Protocol):
    def health(self) -> HealthStatus:
        """Return project-tool availability without launching SC2."""

    def execute(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> Sc2Execution:
        """Execute one bounded structured project operation."""


class LocalSc2Backend:
    """Directory/ZIP project backend with safe working-copy semantics."""

    _entity_prefixes = ("unit", "weapon", "effect", "upgrade", "actor")

    def __init__(
        self,
        *,
        workspace_root: str | Path = ".",
        artifact_root: str | Path = "artifacts",
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.artifact_root = (self.workspace_root / Path(artifact_root)).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="sc2",
            status="ok",
            ready=True,
            details={
                "backend": "structured_directory_and_zip",
                "project_tools_available": True,
                "game_or_editor_automation": False,
                "control_enabled": True,
                "workspace_root": str(self.workspace_root),
                "artifact_root": str(self.artifact_root),
                "gui_fallback": "disabled_until_audited",
            },
        )

    def execute(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> Sc2Execution:
        started = time.perf_counter()
        try:
            if action == "sc2.project.inspect":
                result = self._inspect(target or parameters.get("project"))
            elif action == "sc2.project.snapshot":
                result = self._snapshot(target or parameters.get("project"), parameters)
            elif action == "sc2.project.unpack":
                result = self._unpack(target or parameters.get("project"), parameters)
            elif action in {"sc2.project.pack", "sc2.package"}:
                result = self._pack(target or parameters.get("project"), parameters)
            elif action == "sc2.search":
                result = self._search(target or parameters.get("project"), parameters)
            elif action.endswith(".read") or action == "sc2.trigger.inspect":
                result = self._read_structured(
                    action, target or parameters.get("project"), parameters
                )
            elif action == "sc2.galaxy.validate":
                result = self._validate_galaxy(target or parameters.get("project"))
            elif action.endswith(".modify") or action in {"sc2.galaxy.patch", "sc2.trigger.modify"}:
                result = self._modify(target or parameters.get("project"), parameters)
            elif action == "sc2.test.collect_logs":
                result = self._collect_logs(target or parameters.get("project"))
            elif action in {"sc2.editor.launch", "sc2.map.test"}:
                result = Sc2Execution(
                    success=False,
                    summary="SC2 editor/game launch is intentionally not enabled.",
                    error="sc2_runtime_unavailable",
                    warnings=(
                        "Structured project inspection remains available; GUI is fallback-only.",
                    ),
                    reversible=False,
                )
            else:
                result = Sc2Execution(
                    success=False,
                    summary=f"{action} is defined but not implemented by the local SC2 bridge.",
                    error="not_implemented",
                )
        except (
            OSError,
            ValueError,
            zipfile.BadZipFile,
            ElementTree.ParseError,
            json.JSONDecodeError,
        ) as exc:
            result = Sc2Execution(
                success=False,
                summary="The SC2 request was rejected by the local bridge.",
                error="sc2_request_invalid",
                warnings=(str(exc),),
            )
        return Sc2Execution(
            success=result.success,
            summary=result.summary,
            changed_files=result.changed_files,
            artifacts=result.artifacts,
            data=result.data,
            logs=result.logs,
            warnings=result.warnings,
            error=result.error,
            reversible=result.reversible,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _inspect(self, value: object) -> Sc2Execution:
        source = self._resolve_project(value, must_exist=True)
        if source.is_dir():
            files = self._files(source)
            data = {"project": self._relative(source), "kind": "directory", "files": files}
        else:
            with zipfile.ZipFile(source) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
            data = {"project": self._relative(source), "kind": "archive", "files": names}
        return Sc2Execution(True, f"Inspected SC2 project {self._relative(source)}.", data=data)

    def _snapshot(self, value: object, parameters: Mapping[str, object]) -> Sc2Execution:
        source = self._resolve_project(value, must_exist=True)
        destination_value = parameters.get("destination")
        if destination_value is None:
            destination = self.artifact_root / "sc2" / f"{source.stem}-snapshot-{uuid4().hex[:8]}"
        else:
            destination = self._resolve_path(destination_value)
        if destination == source or source in destination.parents:
            raise ValueError("SC2 snapshot destination must not contain the source")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=False)
        else:
            destination = destination.with_suffix(source.suffix)
            shutil.copy2(source, destination)
        relative = self._relative(destination)
        return Sc2Execution(
            True,
            f"Created an SC2 working snapshot at {relative}.",
            changed_files=(relative,),
            artifacts=(relative,),
            data={"source": self._relative(source), "working_copy": relative},
        )

    def _unpack(self, value: object, parameters: Mapping[str, object]) -> Sc2Execution:
        source = self._resolve_project(value, must_exist=True)
        if source.is_dir():
            return Sc2Execution(False, "The project is already unpacked.", error="already_unpacked")
        destination = self._resolve_path(
            parameters.get("destination") or (self.artifact_root / "sc2" / source.stem)
        )
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                member_path = (destination / member.filename).resolve()
                try:
                    member_path.relative_to(destination.resolve())
                except ValueError as exc:
                    raise ValueError("archive contains a path outside its destination") from exc
            archive.extractall(destination)
        relative = self._relative(destination)
        return Sc2Execution(
            True,
            f"Unpacked SC2 project to {relative}.",
            artifacts=(relative,),
            changed_files=(relative,),
        )

    def _pack(self, value: object, parameters: Mapping[str, object]) -> Sc2Execution:
        source = self._resolve_project(value, must_exist=True)
        if not source.is_dir():
            raise ValueError("SC2 packaging requires an unpacked project directory")
        destination = self._resolve_path(
            parameters.get("destination") or (self.artifact_root / "sc2" / f"{source.name}.SC2Mod")
        )
        if destination == source or source in destination.parents:
            raise ValueError("SC2 package destination must not be inside the source project")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in source.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(source).as_posix())
        relative = self._relative(destination)
        return Sc2Execution(
            True,
            f"Packaged SC2 project at {relative}.",
            artifacts=(relative,),
            changed_files=(relative,),
        )

    def _search(self, value: object, parameters: Mapping[str, object]) -> Sc2Execution:
        project = self._resolve_project(value, must_exist=True)
        query = parameters.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("sc2.search requires a non-empty query")
        if not project.is_dir():
            return self._search_archive(project, query)
        matches: list[dict[str, object]] = []
        for file in project.rglob("*"):
            if not file.is_file() or file.stat().st_size > 2_000_000:
                continue
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, start=1):
                if query.casefold() in line.casefold():
                    matches.append(
                        {"file": self._relative(file), "line": number, "text": line[:500]}
                    )
        return Sc2Execution(
            True, f"Found {len(matches)} SC2 matches.", data={"query": query, "matches": matches}
        )

    def _search_archive(self, archive_path: Path, query: str) -> Sc2Execution:
        matches: list[dict[str, object]] = []
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if name.endswith("/"):
                    continue
                try:
                    text = archive.read(name).decode("utf-8")
                except (UnicodeDecodeError, KeyError):
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if query.casefold() in line.casefold():
                        matches.append({"file": name, "line": number, "text": line[:500]})
        return Sc2Execution(
            True,
            f"Found {len(matches)} SC2 archive matches.",
            data={"query": query, "matches": matches},
        )

    def _read_structured(
        self, action: str, value: object, parameters: Mapping[str, object]
    ) -> Sc2Execution:
        project = self._resolve_project(value, must_exist=True)
        entity = action.split(".")[1] if action.count(".") >= 2 else "trigger"
        query = parameters.get("id") or parameters.get("name") or parameters.get("query")
        records: list[dict[str, object]] = []
        files = self._iter_files(project)
        for relative, content in files:
            if not relative.casefold().endswith((".xml", ".json", ".txt")):
                continue
            if relative.casefold().endswith(".json"):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping) and (
                    query is None or str(query).casefold() in json.dumps(parsed).casefold()
                ):
                    records.append({"file": relative, "record": parsed})
                continue
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError:
                continue
            for element in root.iter():
                haystack = " ".join([element.tag, *element.attrib.values(), element.text or ""])
                if query is None or str(query).casefold() in haystack.casefold():
                    records.append(
                        {
                            "file": relative,
                            "tag": element.tag,
                            "attributes": dict(element.attrib),
                            "text": (element.text or "").strip(),
                        }
                    )
        return Sc2Execution(
            True,
            f"Read {len(records)} SC2 {entity} records.",
            data={"entity": entity, "records": records},
        )

    def _validate_galaxy(self, value: object) -> Sc2Execution:
        project = self._resolve_project(value, must_exist=True)
        files = self._iter_files(project)
        findings: list[dict[str, object]] = []
        checked = 0
        for relative, content in files:
            if not relative.casefold().endswith((".galaxy", ".inc", ".trigger")):
                continue
            checked += 1
            if "\x00" in content:
                findings.append({"file": relative, "error": "nul_byte"})
            if content.count("{") != content.count("}"):
                findings.append({"file": relative, "error": "unbalanced_braces"})
            if content.count('"') % 2:
                findings.append({"file": relative, "error": "unbalanced_quotes"})
        return Sc2Execution(
            not findings,
            "SC2 Galaxy validation passed."
            if not findings
            else "SC2 Galaxy validation found issues.",
            data={"checked_files": checked, "findings": findings},
            error=None if not findings else "sc2_validation_failed",
        )

    def _modify(self, value: object, parameters: Mapping[str, object]) -> Sc2Execution:
        project = self._resolve_project(value, must_exist=True)
        if not project.is_dir():
            raise ValueError("SC2 modifications require an unpacked working-copy directory")
        relative_file = parameters.get("file")
        search = parameters.get("search")
        replacement = parameters.get("replace", "")
        if not isinstance(relative_file, str) or not isinstance(search, str) or not search:
            raise ValueError("SC2 modification requires file and non-empty search values")
        if not isinstance(replacement, str):
            raise ValueError("SC2 replacement must be a string")
        file = self._resolve_path(relative_file, base=project, must_exist=True)
        if file.suffix.casefold() not in {".xml", ".galaxy", ".inc", ".txt", ".json", ".trigger"}:
            raise ValueError("SC2 modification is restricted to structured text files")
        content = file.read_text(encoding="utf-8")
        count = content.count(search)
        if count == 0:
            return Sc2Execution(
                False, "SC2 modification found no matching text.", error="search_not_found"
            )
        updated = content.replace(search, replacement, 1)
        file.write_text(updated, encoding="utf-8")
        relative = self._relative(file)
        return Sc2Execution(
            True,
            f"Patched one occurrence in {relative}.",
            changed_files=(relative,),
            data={"replacements": 1},
        )

    def _collect_logs(self, value: object) -> Sc2Execution:
        project = self._resolve_project(value, must_exist=True)
        logs: list[dict[str, object]] = []
        for file in self._iter_paths(project):
            if file.suffix.casefold() in {".log", ".txt"} and "log" in file.name.casefold():
                try:
                    logs.append(
                        {
                            "file": self._relative(file),
                            "text": file.read_text(encoding="utf-8")[-20_000:],
                        }
                    )
                except UnicodeDecodeError:
                    continue
        return Sc2Execution(True, f"Collected {len(logs)} SC2 log files.", data={"logs": logs})

    def _resolve_project(self, value: object, *, must_exist: bool) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError("an SC2 project path is required")
        path = self._resolve_path(value, must_exist=must_exist)
        if path.is_file() and path.suffix.casefold() not in {".sc2map", ".sc2mod", ".zip"}:
            raise ValueError("SC2 targets must be directories or .SC2Map/.SC2Mod/.zip files")
        return path

    def _resolve_path(
        self, value: object, *, base: Path | None = None, must_exist: bool = False
    ) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError("a path is required")
        candidate = Path(value).expanduser()
        root = self.workspace_root if base is None else base.resolve()
        resolved = (root / candidate if not candidate.is_absolute() else candidate).resolve(
            strict=False
        )
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("SC2 paths must remain inside the workspace or working copy") from exc
        if must_exist and not resolved.exists():
            raise ValueError(f"SC2 path does not exist: {resolved}")
        return resolved

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.workspace_root).as_posix()

    def _files(self, root: Path) -> list[dict[str, object]]:
        return [
            {"path": self._relative(file), "size": file.stat().st_size}
            for file in self._iter_paths(root)
        ]

    def _iter_paths(self, root: Path) -> list[Path]:
        return [path for path in root.rglob("*") if path.is_file()]

    def _iter_files(self, root: Path) -> list[tuple[str, str]]:
        if not root.is_dir():
            with zipfile.ZipFile(root) as archive:
                result: list[tuple[str, str]] = []
                for name in archive.namelist():
                    if name.endswith("/"):
                        continue
                    try:
                        result.append((name, archive.read(name).decode("utf-8")))
                    except UnicodeDecodeError:
                        continue
                return result
        result = []
        for file in self._iter_paths(root):
            try:
                result.append((self._relative(file), file.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                continue
        return result


class Sc2Integration(SkeletonIntegration):
    """Central-permission adapter for structured SC2 project operations."""

    provider_name = "sc2"
    _capabilities = SC2_ACTIONS

    def __init__(
        self,
        permissions: PermissionService | None = None,
        *,
        workspace_root: str | Path = ".",
        artifact_root: str | Path = "artifacts",
        backend: Sc2Backend | None = None,
    ) -> None:
        self.permissions = permissions
        self._backend = backend or LocalSc2Backend(
            workspace_root=workspace_root, artifact_root=artifact_root
        )

    def health(self) -> HealthStatus:
        if self.permissions is None:
            return super().health()
        backend = self._backend.health()
        details = dict(backend.details)
        details.update(
            {"permission_policy": self.permissions.policy.source, "central_authorization": True}
        )
        return HealthStatus(self.provider_name, backend.status, backend.ready, details)

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        if self.permissions is None:
            return ToolResult(
                False,
                action,
                action,
                target=target,
                summary=f"{action} is not configured.",
                error="not_implemented",
            )
        params = dict(parameters or {})
        approval_id = params.get("approval_id")
        if approval_id is not None and not isinstance(approval_id, str):
            return ToolResult(
                False,
                action,
                action,
                target=target,
                summary="approval_id must be a string.",
                error="invalid_approval_id",
            )
        decision = self.permissions.authorize(
            action, target=target, parameters=params, approval_id=approval_id
        )
        if not decision.allowed:
            return self._denied(action, target, decision)
        execution = self._backend.execute(
            action, target=target, parameters=self.permissions.sanitized_parameters(params)
        )
        data = dict(execution.data or {})
        data["permission"] = decision.to_dict()
        return ToolResult(
            success=execution.success,
            tool=action,
            action=action,
            target=target,
            summary=execution.summary,
            changed_files=execution.changed_files,
            artifacts=execution.artifacts,
            data=data,
            logs=execution.logs,
            warnings=execution.warnings,
            error=execution.error,
            reversible=execution.reversible,
            approval_level=decision.level,
            duration_ms=execution.duration_ms,
        )

    @staticmethod
    def _denied(action: str, target: str | None, decision: PermissionDecision) -> ToolResult:
        return ToolResult(
            False,
            action,
            action,
            target=target,
            summary="SC2 action was not authorized.",
            data={"permission": decision.to_dict()},
            warnings=("No SC2 project operation was invoked.",),
            error=decision.error,
            approval_level=decision.level,
        )
