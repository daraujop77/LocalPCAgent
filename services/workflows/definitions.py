"""Standard Blender and SC2 workflow graphs used by the local gateway."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from personal_ai.contracts import ToolResult
from personal_ai.memory import MemoryService
from services.workflows.service import WorkflowDefinition, WorkflowNode, WorkflowPause


def blender_workflow(provider: Any, memory: MemoryService) -> WorkflowDefinition:
    """Build the snapshot -> inspect -> modify -> validate -> preview graph."""

    def snapshot(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke(
            "blender.save_copy",
            target=_required(state, "source"),
            parameters={"destination": state.get("working_copy_destination")},
        )
        _raise_for_result(result)
        working = str(result.data["working_copy"])
        return {"working_path": working, "artifacts": _append(state, "artifacts", result.artifacts)}

    def inspect(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke("blender.inspect_scene", target=_required(state, "working_path"))
        _raise_for_result(result)
        return {"scene": dict(result.data)}

    def modify(state: dict[str, Any]) -> Mapping[str, object]:
        operations = state.get("operations", [])
        if not operations:
            return {"modification_skipped": True}
        result = provider.invoke(
            "blender.execute_bpy",
            target=_required(state, "working_path"),
            parameters={"operations": operations, "approval_id": state.get("approval_id")},
        )
        _raise_for_result(result)
        return {"changed_files": _append(state, "changed_files", result.changed_files)}

    def validate(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke("blender.inspect_scene", target=_required(state, "working_path"))
        _raise_for_result(result)
        return {"validated": True, "validation": dict(result.data)}

    def preview(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke(
            "blender.render.preview",
            target=_required(state, "working_path"),
            parameters={"output": state.get("preview_output")},
        )
        _raise_for_result(result)
        return {"artifacts": _append(state, "artifacts", result.artifacts)}

    def record(state: dict[str, Any]) -> Mapping[str, object]:
        episode = memory.episodes.record(
            run_id=str(state.get("run_id", "workflow")),
            workflow="blender.autonomous",
            task=str(state.get("task", "Blender workflow")),
            success=True,
            summary="Blender snapshot, inspection, modification, validation, and preview completed.",
            inputs={"source": state.get("source"), "operations": state.get("operations", [])},
            outputs={
                "working_path": state.get("working_path"),
                "artifacts": state.get("artifacts", []),
            },
            artifacts=state.get("artifacts", []),
        )
        return {"episode_id": episode.episode_id}

    return WorkflowDefinition(
        name="blender.autonomous",
        description="Preserve a Blender source, inspect, apply controlled operations, validate, and render a preview.",
        nodes=tuple(
            WorkflowNode(name, handler)
            for name, handler in (
                ("snapshot_source", snapshot),
                ("inspect_scene", inspect),
                ("modify_scene", modify),
                ("validate_scene", validate),
                ("render_preview", preview),
                ("record_experience", record),
            )
        ),
    )


def sc2_workflow(provider: Any, memory: MemoryService) -> WorkflowDefinition:
    """Build the snapshot -> inspect -> patch -> validate -> package graph."""

    def snapshot(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke(
            "sc2.project.snapshot",
            target=_required(state, "source"),
            parameters={"destination": state.get("working_copy_destination")},
        )
        _raise_for_result(result)
        return {
            "working_path": result.data["working_copy"],
            "artifacts": _append(state, "artifacts", result.artifacts),
        }

    def inspect(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke("sc2.project.inspect", target=_required(state, "working_path"))
        _raise_for_result(result)
        return {"project_index": dict(result.data)}

    def patch(state: dict[str, Any]) -> Mapping[str, object]:
        if not state.get("patch"):
            return {"patch_skipped": True}
        patch = state["patch"]
        if not isinstance(patch, Mapping):
            raise ValueError("patch must be an object")
        result = provider.invoke(
            "sc2.galaxy.patch",
            target=_required(state, "working_path"),
            parameters={**dict(patch), "approval_id": state.get("approval_id")},
        )
        _raise_for_result(result)
        return {"changed_files": _append(state, "changed_files", result.changed_files)}

    def validate(state: dict[str, Any]) -> Mapping[str, object]:
        result = provider.invoke("sc2.galaxy.validate", target=_required(state, "working_path"))
        _raise_for_result(result)
        return {"validated": result.success, "validation": dict(result.data)}

    def package(state: dict[str, Any]) -> Mapping[str, object]:
        if not state.get("package", True):
            return {"package_skipped": True}
        result = provider.invoke(
            "sc2.package",
            target=_required(state, "working_path"),
            parameters={"destination": state.get("package_output")},
        )
        _raise_for_result(result)
        return {"artifacts": _append(state, "artifacts", result.artifacts)}

    def record(state: dict[str, Any]) -> Mapping[str, object]:
        episode = memory.episodes.record(
            run_id=str(state.get("run_id", "workflow")),
            workflow="sc2.modification",
            task=str(state.get("task", "SC2 workflow")),
            success=True,
            summary="SC2 project snapshot, inspection, patch, validation, and packaging completed.",
            inputs={"source": state.get("source"), "patch": state.get("patch", {})},
            outputs={
                "working_path": state.get("working_path"),
                "artifacts": state.get("artifacts", []),
            },
            artifacts=state.get("artifacts", []),
        )
        return {"episode_id": episode.episode_id}

    return WorkflowDefinition(
        name="sc2.modification",
        description="Preserve an SC2 project, inspect structured data, patch a working copy, validate, and package it.",
        nodes=tuple(
            WorkflowNode(name, handler)
            for name, handler in (
                ("snapshot_project", snapshot),
                ("index_project", inspect),
                ("patch_working_copy", patch),
                ("static_validation", validate),
                ("package_version", package),
                ("record_experience", record),
            )
        ),
    )


def _required(state: Mapping[str, object], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow state requires {key}")
    return value


def _append(state: Mapping[str, object], key: str, values: tuple[str, ...]) -> list[str]:
    existing = state.get(key, [])
    return [str(item) for item in existing] + [str(item) for item in values]


def _raise_for_result(result: ToolResult) -> None:
    if result.success:
        return
    if result.error in {"approval_required", "approval_requested"}:
        raise WorkflowPause(
            "Workflow is waiting for explicit action approval.", approval_required=True
        )
    raise RuntimeError(result.error or result.summary)
