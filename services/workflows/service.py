"""Durable graph-compatible workflow service.

This module deliberately keeps the execution contract independent of a
particular graph library. Nodes are explicit callables, state is checkpointed
after every node, and a later LangGraph adapter can use the same run shape and
event stream without changing integration contracts.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from personal_ai.contracts import HealthStatus

logger = logging.getLogger(__name__)

WorkflowHandler = Callable[[dict[str, Any]], Mapping[str, object] | None]


class WorkflowPause(Exception):
    """Signal that a node needs approval or external input before continuing."""

    def __init__(self, reason: str, *, approval_required: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.approval_required = approval_required


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    name: str
    handler: WorkflowHandler


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    name: str
    nodes: tuple[WorkflowNode, ...]
    description: str = ""


@dataclass(slots=True)
class WorkflowRun:
    run_id: str
    workflow: str
    task: str
    status: str
    state: dict[str, Any]
    project_path: str | None = None
    working_path: str | None = None
    plan: tuple[str, ...] = ()
    current_step: str | None = None
    current_step_index: int = 0
    artifacts: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    approval_required: bool = False
    approval_status: str | None = None
    iteration: int = 0
    model_history: tuple[str, ...] = ()
    tool_history: tuple[str, ...] = ()
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for name in (
            "plan",
            "artifacts",
            "changed_files",
            "warnings",
            "errors",
            "model_history",
            "tool_history",
        ):
            result[name] = list(result[name])
        return result


class WorkflowService:
    """Thread-safe durable workflow runner with JSON checkpoints and events."""

    def __init__(self, storage_root: str | Path = "artifacts/workflows") -> None:
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.runs_path = self.storage_root / "runs.json"
        self.events_path = self.storage_root / "events.jsonl"
        self._runs: dict[str, WorkflowRun] = {}
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._pause_requested: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._lock = threading.RLock()
        self._load_runs()

    def health(self) -> HealthStatus:
        with self._lock:
            counts: dict[str, int] = {}
            for run in self._runs.values():
                counts[run.status] = counts.get(run.status, 0) + 1
        return HealthStatus(
            name="workflows",
            status="ok",
            ready=True,
            details={
                "engine": "durable_graph_compatible",
                "persistence": "json_checkpoints_and_jsonl_events",
                "langgraph_available": importlib.util.find_spec("langgraph") is not None,
                "registered_workflows": sorted(self._definitions),
                "run_counts": counts,
                "pause_resume_cancel": True,
            },
        )

    def register(self, definition: WorkflowDefinition) -> None:
        if not definition.name.strip() or not definition.nodes:
            raise ValueError("workflow definitions require a name and at least one node")
        names = [node.name for node in definition.nodes]
        if len(set(names)) != len(names) or any(not name.strip() for name in names):
            raise ValueError("workflow node names must be unique and non-empty")
        with self._lock:
            self._definitions[definition.name] = definition

    def definitions(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "name": definition.name,
                    "description": definition.description,
                    "nodes": [node.name for node in definition.nodes],
                }
                for definition in self._definitions.values()
            ]

    def start(
        self,
        workflow: str | WorkflowDefinition,
        *,
        task: str = "",
        state: Mapping[str, object] | None = None,
        background: bool = True,
    ) -> WorkflowRun:
        definition = self._resolve_definition(workflow)
        initial_state = _json_copy(dict(state or {}))
        run = WorkflowRun(
            run_id=uuid4().hex,
            workflow=definition.name,
            task=task or str(initial_state.get("task", definition.name)),
            status="queued",
            state=initial_state,
            project_path=_optional_string(initial_state.get("project_path")),
            working_path=_optional_string(initial_state.get("working_path")),
            plan=tuple(node.name for node in definition.nodes),
        )
        initial_state["run_id"] = run.run_id
        run.state = initial_state
        with self._lock:
            self._runs[run.run_id] = run
            self._persist_run(run)
            self._emit(run, "run.created", {"workflow": definition.name})
        if background:
            self._launch(run.run_id, definition)
        else:
            self._execute(run.run_id, definition)
        return self.get(run.run_id)

    def resume(self, run_id: str, *, background: bool = True) -> WorkflowRun:
        with self._lock:
            run = self._require(run_id)
            if run.status not in {"paused", "failed", "queued"}:
                raise ValueError(f"workflow {run_id} cannot resume from {run.status}")
            definition = self._resolve_definition(run.workflow)
            run.status = "queued"
            run.approval_required = False
            run.approval_status = None
            run.iteration += 1
            run.updated_at = _now()
            self._persist_run(run)
            self._emit(run, "run.resumed", {"iteration": run.iteration})
        self._pause_requested.discard(run_id)
        self._cancel_requested.discard(run_id)
        if background:
            self._launch(run_id, definition)
        else:
            self._execute(run_id, definition)
        return self.get(run_id)

    def retry(self, run_id: str, *, background: bool = True) -> WorkflowRun:
        return self.resume(run_id, background=background)

    def pause(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self._require(run_id)
            if run.status in {"completed", "failed", "cancelled"}:
                return self.get(run_id)
            self._pause_requested.add(run_id)
            if run.status == "queued":
                run.status = "paused"
                run.updated_at = _now()
                self._persist_run(run)
                self._emit(run, "run.paused", {"reason": "pause_requested_before_start"})
            return self.get(run_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self._require(run_id)
            if run.status in {"completed", "failed", "cancelled"}:
                return self.get(run_id)
            self._cancel_requested.add(run_id)
            if run.status in {"queued", "paused"}:
                run.status = "cancelled"
                run.updated_at = _now()
                self._persist_run(run)
                self._emit(run, "run.cancelled", {})
            return self.get(run_id)

    def steer(self, run_id: str, instruction: str) -> WorkflowRun:
        clean = instruction.strip()
        if not clean:
            raise ValueError("steering instruction must not be empty")
        with self._lock:
            run = self._require(run_id)
            instructions = list(run.state.get("steering_instructions", []))
            instructions.append(clean)
            run.state["steering_instructions"] = instructions
            run.updated_at = _now()
            self._persist_run(run)
            self._emit(run, "run.steered", {"instruction": clean})
            return self.get(run_id)

    def get(self, run_id: str) -> WorkflowRun:
        with self._lock:
            return _copy_run(self._require(run_id))

    def list_runs(self, *, status: str | None = None) -> list[dict[str, object]]:
        with self._lock:
            runs = [run for run in self._runs.values() if status is None or run.status == status]
            return [
                run.to_dict()
                for run in sorted(runs, key=lambda item: item.started_at, reverse=True)
            ]

    def events(self, run_id: str | None = None) -> list[dict[str, object]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, object]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if run_id is None or event.get("run_id") == run_id:
                events.append(event)
        return events

    def _launch(self, run_id: str, definition: WorkflowDefinition) -> None:
        thread = threading.Thread(
            target=self._execute,
            args=(run_id, definition),
            name=f"workflow-{run_id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._threads[run_id] = thread
        thread.start()

    def _execute(self, run_id: str, definition: WorkflowDefinition) -> None:
        with self._lock:
            run = self._require(run_id)
            if run.status in {"completed", "cancelled"}:
                return
            run.status = "running"
            run.updated_at = _now()
            self._persist_run(run)
            self._emit(run, "run.started", {})

        while True:
            with self._lock:
                run = self._require(run_id)
                if run_id in self._cancel_requested:
                    run.status = "cancelled"
                    run.updated_at = _now()
                    self._persist_run(run)
                    self._emit(run, "run.cancelled", {})
                    return
                if run_id in self._pause_requested:
                    run.status = "paused"
                    run.updated_at = _now()
                    self._persist_run(run)
                    self._emit(run, "run.paused", {"reason": "pause_requested"})
                    return
                if run.current_step_index >= len(definition.nodes):
                    run.status = "completed"
                    run.current_step = None
                    run.updated_at = _now()
                    self._persist_run(run)
                    self._emit(run, "run.completed", {})
                    return
                node = definition.nodes[run.current_step_index]
                run.current_step = node.name
                run.updated_at = _now()
                self._persist_run(run)
                self._emit(run, "workflow.node.started", {"node": node.name})
                state = dict(run.state)

            try:
                result = node.handler(state)
            except WorkflowPause as exc:
                with self._lock:
                    run = self._require(run_id)
                    run.status = "paused"
                    run.approval_required = exc.approval_required
                    run.approval_status = "required" if exc.approval_required else "waiting"
                    run.warnings = (*run.warnings, exc.reason)
                    run.updated_at = _now()
                    self._persist_run(run)
                    self._emit(
                        run, "workflow.node.paused", {"node": node.name, "reason": exc.reason}
                    )
                return
            except Exception as exc:  # noqa: BLE001 - workflow failures are persisted
                logger.exception(
                    "workflow_node_failed", extra={"run_id": run_id, "node": node.name}
                )
                with self._lock:
                    run = self._require(run_id)
                    run.status = "failed"
                    run.errors = (*run.errors, f"{node.name}: {exc}")
                    run.updated_at = _now()
                    self._persist_run(run)
                    self._emit(run, "workflow.node.failed", {"node": node.name, "error": str(exc)})
                return

            with self._lock:
                run = self._require(run_id)
                if result:
                    run.state.update(_json_copy(dict(result)))
                run.tool_history = (*run.tool_history, node.name)
                run.current_step_index += 1
                run.current_step = (
                    definition.nodes[run.current_step_index].name
                    if run.current_step_index < len(definition.nodes)
                    else None
                )
                self._merge_state_fields(run)
                run.updated_at = _now()
                self._persist_run(run)
                self._emit(run, "workflow.node.completed", {"node": node.name})

    def _merge_state_fields(self, run: WorkflowRun) -> None:
        state = run.state
        for field_name in ("project_path", "working_path", "approval_status"):
            value = state.get(field_name)
            if isinstance(value, str):
                setattr(run, field_name, value)
        for field_name in ("artifacts", "changed_files", "warnings", "errors", "model_history"):
            value = state.get(field_name)
            if isinstance(value, list | tuple):
                setattr(run, field_name, tuple(str(item) for item in value))
        if isinstance(state.get("approval_required"), bool):
            run.approval_required = state["approval_required"]

    def _resolve_definition(self, workflow: str | WorkflowDefinition) -> WorkflowDefinition:
        if isinstance(workflow, WorkflowDefinition):
            self.register(workflow)
            return workflow
        with self._lock:
            definition = self._definitions.get(workflow)
        if definition is None:
            raise KeyError(f"unknown workflow: {workflow}")
        return definition

    def _require(self, run_id: str) -> WorkflowRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown workflow run: {run_id}")
        return run

    def _persist_run(self, run: WorkflowRun) -> None:
        records = [item.to_dict() for item in self._runs.values()]
        self.runs_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _emit(self, run: WorkflowRun, event_type: str, details: Mapping[str, object]) -> None:
        event = {
            "event_id": uuid4().hex,
            "event_type": event_type,
            "run_id": run.run_id,
            "workflow": run.workflow,
            "timestamp": _now(),
            "details": _json_copy(dict(details)),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _load_runs(self) -> None:
        if not self.runs_path.exists():
            return
        payload = json.loads(self.runs_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return
        for record in payload:
            if not isinstance(record, Mapping):
                continue
            run = WorkflowRun(
                run_id=str(record.get("run_id", "")),
                workflow=str(record.get("workflow", "")),
                task=str(record.get("task", "")),
                status=(
                    "failed"
                    if record.get("status") == "running"
                    else str(record.get("status", "failed"))
                ),
                state=record.get("state", {}) if isinstance(record.get("state"), dict) else {},
                project_path=_optional_string(record.get("project_path")),
                working_path=_optional_string(record.get("working_path")),
                plan=tuple(str(item) for item in record.get("plan", [])),
                current_step=_optional_string(record.get("current_step")),
                current_step_index=int(record.get("current_step_index", 0)),
                artifacts=tuple(str(item) for item in record.get("artifacts", [])),
                changed_files=tuple(str(item) for item in record.get("changed_files", [])),
                warnings=tuple(str(item) for item in record.get("warnings", [])),
                errors=tuple(str(item) for item in record.get("errors", [])),
                approval_required=bool(record.get("approval_required", False)),
                approval_status=_optional_string(record.get("approval_status")),
                iteration=int(record.get("iteration", 0)),
                model_history=tuple(str(item) for item in record.get("model_history", [])),
                tool_history=tuple(str(item) for item in record.get("tool_history", [])),
                started_at=str(record.get("started_at", _now())),
                updated_at=str(record.get("updated_at", _now())),
            )
            if run.run_id:
                self._runs[run.run_id] = run


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _json_copy(value: object) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _copy_run(run: WorkflowRun) -> WorkflowRun:
    payload = run.to_dict()
    return WorkflowRun(
        run_id=str(payload["run_id"]),
        workflow=str(payload["workflow"]),
        task=str(payload["task"]),
        status=str(payload["status"]),
        state=dict(payload["state"]),
        project_path=payload.get("project_path")
        if isinstance(payload.get("project_path"), str)
        else None,
        working_path=payload.get("working_path")
        if isinstance(payload.get("working_path"), str)
        else None,
        plan=tuple(payload["plan"]),
        current_step=payload.get("current_step")
        if isinstance(payload.get("current_step"), str)
        else None,
        current_step_index=int(payload["current_step_index"]),
        artifacts=tuple(payload["artifacts"]),
        changed_files=tuple(payload["changed_files"]),
        warnings=tuple(payload["warnings"]),
        errors=tuple(payload["errors"]),
        approval_required=bool(payload["approval_required"]),
        approval_status=payload.get("approval_status")
        if isinstance(payload.get("approval_status"), str)
        else None,
        iteration=int(payload["iteration"]),
        model_history=tuple(payload["model_history"]),
        tool_history=tuple(payload["tool_history"]),
        started_at=str(payload["started_at"]),
        updated_at=str(payload["updated_at"]),
    )
