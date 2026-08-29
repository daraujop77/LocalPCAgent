"""Controlled Blender bridge with a replaceable headless backend.

The provider never edits a source file in place. The default backend uses
Blender's background CLI when it is installed and also supports JSON scene
fixtures for deterministic development tests.
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from personal_ai.contracts import HealthStatus, ToolResult
from personal_ai.integration import SkeletonIntegration
from personal_ai.permissions import PermissionDecision, PermissionService

logger = logging.getLogger(__name__)

BLENDER_ACTIONS = (
    "blender.status",
    "blender.open_file",
    "blender.save_copy",
    "blender.inspect_scene",
    "blender.list_objects",
    "blender.inspect_object",
    "blender.import_asset",
    "blender.export_asset",
    "blender.execute_bpy",
    "blender.material.create",
    "blender.material.modify",
    "blender.object.transform",
    "blender.object.modify",
    "blender.camera.configure",
    "blender.render.preview",
    "blender.render.final",
    "blender.capture_viewport",
)

# Keep future policy action names reserved without advertising them as
# callable capabilities before they have a backend implementation.
BLENDER_IMPLEMENTED_ACTIONS = (
    "blender.status",
    "blender.open_file",
    "blender.save_copy",
    "blender.inspect_scene",
    "blender.list_objects",
    "blender.inspect_object",
    "blender.execute_bpy",
    "blender.material.create",
    "blender.material.modify",
    "blender.object.transform",
    "blender.camera.configure",
    "blender.render.preview",
    "blender.render.final",
)


@dataclass(frozen=True, slots=True)
class BlenderExecution:
    success: bool
    summary: str
    changed_files: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    data: Mapping[str, object] = field(default_factory=dict)
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None
    reversible: bool = True
    duration_ms: int | None = None


class BlenderBackend(Protocol):
    def health(self) -> HealthStatus:
        """Return availability without opening or changing a scene."""

    def execute(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> BlenderExecution:
        """Execute one validated high-level Blender operation."""


class LocalBlenderBackend:
    """Headless Blender CLI backend with bounded fixture support."""

    _supported = {
        "blender.status",
        "blender.open_file",
        "blender.save_copy",
        "blender.inspect_scene",
        "blender.list_objects",
        "blender.inspect_object",
        "blender.execute_bpy",
        "blender.object.transform",
        "blender.material.create",
        "blender.material.modify",
        "blender.camera.configure",
        "blender.render.preview",
        "blender.render.final",
    }

    def __init__(
        self,
        *,
        workspace_root: str | Path = ".",
        artifact_root: str | Path = "artifacts",
        executable: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        artifact_path = Path(artifact_root).expanduser()
        self.artifact_root = (self.workspace_root / artifact_path).resolve()
        try:
            self.artifact_root.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("Blender artifacts must remain inside the workspace") from exc
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.executable = self._resolve_executable(executable)
        self.timeout_seconds = timeout_seconds

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="blender",
            status="ok",
            ready=True,
            details={
                "backend": "headless_cli_and_json_fixture",
                "implemented_actions": list(BLENDER_IMPLEMENTED_ACTIONS),
                "executable": self.executable,
                "blender_available": self.executable is not None,
                "control_enabled": self.executable is not None,
                "workspace_root": str(self.workspace_root),
                "artifact_root": str(self.artifact_root),
                "source_preservation": True,
                "gui_fallback": "not_implemented",
            },
        )

    def execute(
        self,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> BlenderExecution:
        started = time.perf_counter()
        try:
            if action == "blender.status":
                result = BlenderExecution(
                    success=True,
                    summary="Blender bridge status is available.",
                    data=self.health().details,
                )
            elif action in {
                "blender.inspect_scene",
                "blender.open_file",
                "blender.list_objects",
                "blender.inspect_object",
            }:
                result = self._inspect(action, target, parameters)
            elif action == "blender.save_copy":
                result = self._save_copy(target, parameters)
            elif action in {
                "blender.execute_bpy",
                "blender.object.transform",
                "blender.material.create",
                "blender.material.modify",
                "blender.camera.configure",
            }:
                result = self._execute_bpy(action, target, parameters)
            elif action in {"blender.render.preview", "blender.render.final"}:
                result = self._render(action, target, parameters)
            else:
                result = BlenderExecution(
                    success=False,
                    summary=f"{action} is defined but not implemented by the local bridge.",
                    error="not_implemented",
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result = BlenderExecution(
                success=False,
                summary="The Blender request was rejected by the local bridge.",
                error="blender_request_invalid",
                warnings=(str(exc),),
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return BlenderExecution(
            success=result.success,
            summary=result.summary,
            changed_files=result.changed_files,
            artifacts=result.artifacts,
            data=result.data,
            logs=result.logs,
            warnings=result.warnings,
            error=result.error,
            reversible=result.reversible,
            duration_ms=duration_ms,
        )

    def _inspect(
        self,
        action: str,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> BlenderExecution:
        source = self._resolve_file(target or parameters.get("source"), must_exist=True)
        if source.suffix.casefold() in {".json", ".scene"}:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("scene fixture must contain a JSON object")
            objects = payload.get("objects", [])
            if action == "blender.inspect_object":
                wanted = parameters.get("object")
                objects = [
                    item
                    for item in objects
                    if isinstance(item, Mapping) and item.get("name") == wanted
                ]
            if action == "blender.list_objects":
                payload = {"objects": objects if isinstance(objects, Sequence) else []}
            return BlenderExecution(
                success=True,
                summary=f"Inspected Blender fixture {self._relative(source)}.",
                data={"source": self._relative(source), "scene": dict(payload), "fixture": True},
            )
        if self.executable is None:
            return BlenderExecution(
                success=False,
                summary="A Blender executable is not configured for .blend inspection.",
                error="blender_unavailable",
                warnings=("JSON scene fixtures remain available for deterministic tests.",),
            )
        expression = (
            "import bpy,json; print('PERSONAL_AI_SCENE=' + json.dumps({"
            "'objects':[{'name':o.name,'type':o.type} for o in bpy.data.objects],"
            "'materials':[m.name for m in bpy.data.materials]}))"
        )
        completed = self._run(["--background", str(source), "--python-expr", expression])
        marker = next(
            (
                line
                for line in completed.stdout.splitlines()
                if line.startswith("PERSONAL_AI_SCENE=")
            ),
            None,
        )
        data: dict[str, object] = {
            "source": self._relative(source),
            "return_code": completed.returncode,
        }
        if marker:
            parsed = json.loads(marker.removeprefix("PERSONAL_AI_SCENE="))
            if isinstance(parsed, Mapping):
                data.update(parsed)
        return BlenderExecution(
            success=completed.returncode == 0,
            summary="Inspected Blender scene through background mode.",
            data=data,
            logs=tuple(completed.stdout.splitlines()[-20:]),
            warnings=tuple(completed.stderr.splitlines()[-10:]),
            error=None if completed.returncode == 0 else "blender_command_failed",
        )

    def _save_copy(self, target: str | None, parameters: Mapping[str, object]) -> BlenderExecution:
        source = self._resolve_file(target or parameters.get("source"), must_exist=True)
        if source.suffix.casefold() not in {".blend", ".json", ".scene"}:
            raise ValueError("Blender working copies are restricted to .blend or scene fixtures")
        destination_value = parameters.get("destination")
        if destination_value is None:
            destination = (
                self.artifact_root / "blender" / f"{source.stem}-{uuid4().hex[:8]}{source.suffix}"
            )
        else:
            destination = self._resolve_file(destination_value, must_exist=False)
        if destination == source:
            raise ValueError("Blender working copy must differ from the source")
        self._require_artifact_path(destination, "working copy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        relative = self._relative(destination)
        return BlenderExecution(
            success=True,
            summary=f"Created a Blender working copy at {relative}.",
            changed_files=(relative,),
            artifacts=(relative,),
            data={"source": self._relative(source), "working_copy": relative},
        )

    def _execute_bpy(
        self,
        action: str,
        target: str | None,
        parameters: Mapping[str, object],
    ) -> BlenderExecution:
        source = self._resolve_file(target or parameters.get("working_copy"), must_exist=True)
        if source.suffix.casefold() != ".blend":
            raise ValueError("controlled bpy operations require a .blend working copy")
        self._require_working_copy(source)
        operations = parameters.get("operations")
        if operations is None:
            operations = [self._operation_for_action(action, parameters)]
        if (
            not isinstance(operations, Sequence)
            or isinstance(operations, (str, bytes))
            or not operations
        ):
            raise ValueError("operations must be a non-empty array")
        normalized = [self._validate_operation(item) for item in operations]
        if self.executable is None:
            return BlenderExecution(
                success=False,
                summary="A Blender executable is not configured for controlled bpy execution.",
                error="blender_unavailable",
            )
        encoded = json.dumps(normalized, ensure_ascii=False)
        script = (
            "import bpy,json\n"
            f"ops=json.loads({encoded!r})\n"
            "for item in ops:\n"
            "    op=item['op']\n"
            "    if op == 'set_render_engine':\n"
            "        bpy.context.scene.render.engine=item['value']\n"
            "    elif op == 'transform':\n"
            "        obj=bpy.data.objects.get(item['object'])\n"
            "        if obj is None: raise ValueError('object not found')\n"
            "        if 'location' in item: obj.location=item['location']\n"
            "        if 'rotation_euler' in item: obj.rotation_euler=item['rotation_euler']\n"
            "        if 'scale' in item: obj.scale=item['scale']\n"
            "    elif op == 'material_color':\n"
            "        obj=bpy.data.objects.get(item['object'])\n"
            "        if obj is None or obj.active_material is None: raise ValueError('material not found')\n"
            "        obj.active_material.diffuse_color=(*item['color'], 1.0)\n"
            "    elif op == 'material_create':\n"
            "        obj=bpy.data.objects.get(item['object'])\n"
            "        if obj is None or not hasattr(obj, 'data') or not hasattr(obj.data, 'materials'): raise ValueError('material target not found')\n"
            "        material=bpy.data.materials.new(name=item.get('name') or (obj.name + 'Material'))\n"
            "        material.diffuse_color=(*item['color'], 1.0)\n"
            "        obj.data.materials.append(material)\n"
            "    elif op == 'camera_configure':\n"
            "        camera=bpy.data.objects.get(item['object'])\n"
            "        if camera is None: raise ValueError('camera not found')\n"
            "        if 'location' in item: camera.location=item['location']\n"
            "        if 'rotation_euler' in item: camera.rotation_euler=item['rotation_euler']\n"
            "bpy.ops.wm.save_as_mainfile(filepath=" + repr(str(source)) + ")\n"
        )
        completed = self._run(["--background", str(source), "--python-expr", script])
        relative = self._relative(source)
        return BlenderExecution(
            success=completed.returncode == 0,
            summary="Applied controlled bpy operations to the working copy.",
            changed_files=(relative,) if completed.returncode == 0 else (),
            data={"working_copy": relative, "operations": normalized},
            logs=tuple(completed.stdout.splitlines()[-20:]),
            warnings=tuple(completed.stderr.splitlines()[-10:]),
            error=None if completed.returncode == 0 else "blender_command_failed",
        )

    def _render(
        self, action: str, target: str | None, parameters: Mapping[str, object]
    ) -> BlenderExecution:
        source = self._resolve_file(target or parameters.get("working_copy"), must_exist=True)
        output_value = parameters.get("output")
        suffix = "preview" if action.endswith("preview") else "final"
        output = (
            self.artifact_root / "blender" / f"{source.stem}-{suffix}.png"
            if output_value is None
            else self._resolve_file(output_value, must_exist=False)
        )
        self._require_artifact_path(output, "render output")
        output.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.casefold() in {".json", ".scene"}:
            output.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
            relative = self._relative(output)
            return BlenderExecution(
                success=True,
                summary=f"Rendered deterministic fixture {suffix} output.",
                artifacts=(relative,),
                data={"source": self._relative(source), "output": relative, "fixture": True},
            )
        if source.suffix.casefold() != ".blend":
            raise ValueError("rendering requires a .blend working copy or JSON fixture")
        self._require_working_copy(source)
        if self.executable is None:
            return BlenderExecution(
                success=False,
                summary="A Blender executable is not configured for rendering.",
                error="blender_unavailable",
            )
        script = (
            "import bpy; bpy.context.scene.render.filepath="
            + repr(str(output))
            + "; bpy.ops.render.render(write_still=True)"
        )
        completed = self._run(["--background", str(source), "--python-expr", script])
        relative = self._relative(output)
        return BlenderExecution(
            success=completed.returncode == 0 and output.exists(),
            summary=f"Rendered Blender {suffix} output.",
            artifacts=(relative,) if output.exists() else (),
            data={"source": self._relative(source), "output": relative},
            logs=tuple(completed.stdout.splitlines()[-20:]),
            warnings=tuple(completed.stderr.splitlines()[-10:]),
            error=None
            if completed.returncode == 0 and output.exists()
            else "blender_render_failed",
        )

    @staticmethod
    def _operation_for_action(
        action: str, parameters: Mapping[str, object]
    ) -> Mapping[str, object]:
        mapping = {
            "blender.object.transform": "transform",
            "blender.material.create": "material_create",
            "blender.material.modify": "material_color",
            "blender.camera.configure": "camera_configure",
        }
        operation = mapping.get(action)
        if operation is None:
            raise ValueError("execute_bpy requires explicit operations")
        return {**dict(parameters), "op": operation}

    @staticmethod
    def _validate_operation(value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError("each bpy operation must be an object")
        operation = value.get("op")
        if operation not in {
            "transform",
            "material_create",
            "material_color",
            "camera_configure",
            "set_render_engine",
        }:
            raise ValueError("bpy operation is not allowlisted")
        result = {str(key): value[key] for key in value}
        if operation in {"transform", "material_color", "camera_configure"} and not isinstance(
            result.get("object"), str
        ):
            raise ValueError("bpy object operations require an object name")
        if operation == "set_render_engine" and result.get("value") not in {
            "BLENDER_EEVEE_NEXT",
            "BLENDER_WORKBENCH",
            "BLENDER_RENDER",
        }:
            raise ValueError("render engine is not allowlisted")
        if operation in {"transform", "camera_configure"}:
            for field_name in ("location", "rotation_euler", "scale"):
                if field_name in result and not _vector(result[field_name]):
                    raise ValueError(f"{field_name} must be a numeric three-vector")
        if operation in {"material_create", "material_color"} and not _vector(
            result.get("color"), maximum=1.0
        ):
            raise ValueError("material color must be a numeric three-vector from 0 to 1")
        if operation == "material_create" and (
            "name" in result and not isinstance(result["name"], str)
        ):
            raise ValueError("material name must be a string")
        return result

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *args],
                cwd=self.workspace_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Blender operation timed out") from exc

    def _resolve_file(self, value: object, *, must_exist: bool) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError("a target or source path is required")
        candidate = Path(value).expanduser()
        resolved = (
            self.workspace_root / candidate if not candidate.is_absolute() else candidate
        ).resolve(strict=False)
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("Blender paths must remain inside the workspace") from exc
        if must_exist and not resolved.is_file():
            raise ValueError(f"Blender file does not exist: {resolved}")
        return resolved

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.workspace_root).as_posix()

    def _require_working_copy(self, path: Path) -> None:
        self._require_artifact_path(path, "Blender mutation target")

    def _require_artifact_path(self, path: Path, label: str) -> None:
        try:
            path.resolve(strict=False).relative_to(self.artifact_root)
        except ValueError as exc:
            raise ValueError(f"{label} must remain inside the managed artifact root") from exc

    @staticmethod
    def _resolve_executable(executable: str | None) -> str | None:
        if executable:
            path = Path(executable).expanduser()
            if path.is_file():
                return str(path.resolve())
        return shutil.which(executable or "blender")


def _vector(value: object, *, maximum: float | None = None) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return False
    return maximum is None or all(0 <= float(item) <= maximum for item in value)


class BlenderIntegration(SkeletonIntegration):
    """Central-permission adapter for the Blender backend."""

    provider_name = "blender"
    _capabilities = BLENDER_IMPLEMENTED_ACTIONS

    def __init__(
        self,
        permissions: PermissionService | None = None,
        *,
        workspace_root: str | Path = ".",
        artifact_root: str | Path = "artifacts",
        executable: str | None = None,
        timeout_seconds: float = 300.0,
        backend: BlenderBackend | None = None,
    ) -> None:
        self.permissions = permissions
        self._backend = backend or LocalBlenderBackend(
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            executable=executable,
            timeout_seconds=timeout_seconds,
        )

    def health(self) -> HealthStatus:
        if self.permissions is None:
            return super().health()
        backend = self._backend.health()
        details = dict(backend.details)
        details.update(
            {"permission_policy": self.permissions.policy.source, "central_authorization": True}
        )
        return HealthStatus(
            name=self.provider_name,
            status=backend.status,
            ready=backend.ready,
            details=details,
        )

    def invoke(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> ToolResult:
        if self.permissions is None:
            return ToolResult(
                success=False,
                tool=action,
                action=action,
                target=target,
                summary=f"{action} is defined but not configured with central permissions.",
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
            action,
            target=target,
            parameters=self.permissions.sanitized_parameters(params),
        )
        data = dict(execution.data)
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
            success=False,
            tool=action,
            action=action,
            target=target,
            summary="Blender action was not authorized.",
            data={"permission": decision.to_dict()},
            warnings=("No Blender operation was invoked.",),
            error=decision.error,
            approval_level=decision.level,
        )
