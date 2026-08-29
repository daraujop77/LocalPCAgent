from collections.abc import Sequence

from personal_ai.chat import ChatMessage
from personal_ai.contracts import HealthStatus
from personal_ai.qwen import ModelReply


class FakeQwenClient:
    route_name = "qwen-local"
    model_name = "qwen-test"

    def __init__(self, response: str = "Fake Qwen response") -> None:
        self.response = response
        self.calls: list[tuple[ChatMessage, ...]] = []

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="qwen",
            status="ok",
            ready=True,
            details={"backend": "fake", "model": self.model_name},
        )

    def complete(self, messages: Sequence[ChatMessage], *, request_id: str) -> ModelReply:
        del request_id
        self.calls.append(tuple(messages))
        return ModelReply(content=self.response, model_name=self.model_name)
