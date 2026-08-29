import warnings

import pytest

from personal_ai.memory import MemoryService
from services.workflows.langgraph_adapter import compile_definition
from services.workflows.service import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowPause,
    WorkflowService,
)


def test_workflow_checkpoints_nodes_and_survives_service_reload(tmp_path) -> None:
    def first(state):
        return {"value": state.get("value", 0) + 1}

    def second(state):
        return {"value": state["value"] + 1}

    definition = WorkflowDefinition(
        "fixture.workflow",
        (WorkflowNode("first", first), WorkflowNode("second", second)),
    )
    service = WorkflowService(tmp_path / "runs")
    run = service.start(definition, state={"value": 0}, background=False)

    assert run.status == "completed"
    assert run.state["value"] == 2
    assert [event["event_type"] for event in service.events(run.run_id)][-1] == "run.completed"

    reloaded = WorkflowService(tmp_path / "runs")
    assert reloaded.get(run.run_id).status == "completed"
    assert reloaded.get(run.run_id).state["value"] == 2


def test_workflow_pause_and_resume_from_checkpoint(tmp_path) -> None:
    calls = []

    def wait_for_input(state):
        if "approved" not in state.get("steering_instructions", []):
            raise WorkflowPause("waiting for approval", approval_required=True)
        calls.append("continued")
        return {"done": True}

    definition = WorkflowDefinition("pause.workflow", (WorkflowNode("wait", wait_for_input),))
    service = WorkflowService(tmp_path / "runs")
    paused = service.start(definition, state={}, background=False)

    assert paused.status == "paused"
    assert paused.approval_required is True
    service.steer(paused.run_id, "approved")
    resumed = service.resume(paused.run_id, background=False)

    assert resumed.status == "completed"
    assert calls == ["continued"]


def test_workflow_failure_is_recorded_as_an_episode(tmp_path) -> None:
    memory = MemoryService(tmp_path / "memory")

    def fail(state):
        del state
        raise RuntimeError("fixture failure")

    service = WorkflowService(tmp_path / "runs", memory=memory)
    run = service.start(
        WorkflowDefinition("failure.workflow", (WorkflowNode("fail", fail),)),
        background=False,
    )

    assert run.status == "failed"
    episodes = memory.episodes.list()
    assert len(episodes) == 1
    assert episodes[0].success is False


def test_langgraph_adapter_compiles_the_same_explicit_nodes() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pytest.importorskip("langgraph")
        graph = compile_definition(
            WorkflowDefinition(
                "langgraph.fixture", (WorkflowNode("done", lambda state: {"ok": True}),)
            )
        )

    assert graph.invoke({})["ok"] is True
