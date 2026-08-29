"""Request and message contracts for the Hermes local chat boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["system", "user", "assistant"]


class ChatValidationError(ValueError):
    """Raised when a chat request does not satisfy the public contract."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """Minimal M1 request; conversation history is intentionally not persisted yet."""

    message: str
    conversation_id: str | None = None
    task_type: str = "general"
    system_prompt: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> ChatRequest:
        if not isinstance(payload, Mapping):
            raise ChatValidationError("request body must be a JSON object")

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ChatValidationError("message must be a non-empty string")

        conversation_id = payload.get("conversation_id")
        if conversation_id is not None and not isinstance(conversation_id, str):
            raise ChatValidationError("conversation_id must be a string when provided")

        task_type = payload.get("task_type", "general")
        if not isinstance(task_type, str) or not task_type.strip():
            raise ChatValidationError("task_type must be a non-empty string")

        system_prompt = payload.get("system_prompt")
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise ChatValidationError("system_prompt must be a string when provided")

        return cls(
            message=message.strip(),
            conversation_id=conversation_id,
            task_type=task_type.strip(),
            system_prompt=system_prompt.strip() if system_prompt else None,
        )

    def messages(self) -> tuple[ChatMessage, ...]:
        messages: list[ChatMessage] = []
        if self.system_prompt:
            messages.append(ChatMessage(role="system", content=self.system_prompt))
        messages.append(ChatMessage(role="user", content=self.message))
        return tuple(messages)
