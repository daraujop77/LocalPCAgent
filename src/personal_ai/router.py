"""Deterministic M1 model-routing rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass

QWEN_LOCAL = "qwen-local"
CODEX = "codex"
GROK = "grok"
GEMINI_OPTIONAL = "gemini-optional"

ROUTING_RULES: dict[str, tuple[str, str]] = {
    "repository_implementation": (CODEX, "task_requires_coding_specialist"),
    "difficult_debugging": (CODEX, "task_requires_coding_specialist"),
    "brainstorming": (GROK, "task_requires_ideation_specialist"),
    "adversarial_review": (GROK, "task_requires_critic_specialist"),
    "very_large_document": (GEMINI_OPTIONAL, "task_requires_large_context_specialist"),
}


@dataclass(frozen=True, slots=True)
class ModelSelection:
    task_type: str
    selected_model: str
    reason: str
    fallback_model: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ModelRouter:
    """Small explicit router; learning-based routing is intentionally deferred."""

    def select(self, task_type: str | None) -> ModelSelection:
        normalized_task = (task_type or "general").strip().lower() or "general"
        selected = ROUTING_RULES.get(normalized_task)
        if selected is None:
            return ModelSelection(
                task_type=normalized_task,
                selected_model=QWEN_LOCAL,
                reason="default_local_qwen",
            )
        model, reason = selected
        return ModelSelection(
            task_type=normalized_task,
            selected_model=model,
            reason=reason,
            fallback_model=QWEN_LOCAL,
        )
