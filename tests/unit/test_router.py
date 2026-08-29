import pytest

from personal_ai.router import (
    CODEX,
    GEMINI_OPTIONAL,
    GROK,
    QWEN_LOCAL,
    ModelRouter,
)


@pytest.mark.parametrize(
    ("task_type", "selected_model"),
    [
        ("repository_implementation", CODEX),
        ("difficult_debugging", CODEX),
        ("brainstorming", GROK),
        ("adversarial_review", GROK),
        ("very_large_document", GEMINI_OPTIONAL),
    ],
)
def test_router_applies_explicit_specialist_rules(task_type: str, selected_model: str) -> None:
    selection = ModelRouter().select(task_type)

    assert selection.selected_model == selected_model
    assert selection.fallback_model == QWEN_LOCAL
    assert selection.task_type == task_type


def test_router_defaults_to_local_qwen() -> None:
    selection = ModelRouter().select("ordinary_chat")

    assert selection.selected_model == QWEN_LOCAL
    assert selection.reason == "default_local_qwen"
    assert selection.fallback_model is None
