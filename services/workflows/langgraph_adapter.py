"""Optional LangGraph compilation for the stable workflow definition contract."""

from __future__ import annotations

from typing import Any

from services.workflows.service import WorkflowDefinition


class LangGraphUnavailable(RuntimeError):
    """Raised when the optional workflow extra has not been installed."""


def compile_definition(definition: WorkflowDefinition) -> Any:
    """Compile a definition to LangGraph while preserving its explicit nodes.

    The durable JSON runner remains the gateway default because it owns the
    repository's stable checkpoint format. This adapter lets workflow authors
    evaluate LangGraph locally without changing node handlers or state shape.
    """

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise LangGraphUnavailable(
            "Install the optional workflow extra to compile LangGraph definitions."
        ) from exc

    graph = StateGraph(dict)
    for node in definition.nodes:
        graph.add_node(node.name, node.handler)
    graph.add_edge(START, definition.nodes[0].name)
    for previous, current in zip(definition.nodes, definition.nodes[1:]):
        graph.add_edge(previous.name, current.name)
    graph.add_edge(definition.nodes[-1].name, END)
    return graph.compile()
