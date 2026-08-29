import logging

from personal_ai.chat import ChatRequest
from personal_ai.hermes import HermesService
from personal_ai.router import ModelRouter
from tests.support import FakeQwenClient


def test_hermes_completes_local_chat_and_logs_selection(caplog) -> None:
    client = FakeQwenClient(response="Hello from local Qwen")
    service = HermesService(client, ModelRouter())

    with caplog.at_level(logging.INFO, logger="personal_ai.hermes"):
        response = service.chat(
            ChatRequest(
                message="Hello",
                conversation_id="conversation-1",
                system_prompt="Be concise.",
            )
        )

    assert response.success is True
    assert response.message is not None
    assert response.message.content == "Hello from local Qwen"
    assert response.fallback_used is False
    assert [message.role for message in client.calls[0]] == ["system", "user"]
    assert any(record.message == "model_selected" for record in caplog.records)


def test_hermes_falls_back_to_qwen_for_unconfigured_specialist() -> None:
    client = FakeQwenClient()
    response = HermesService(client, ModelRouter()).chat(
        ChatRequest(message="Review this idea", task_type="adversarial_review")
    )

    assert response.success is True
    assert response.model == "qwen-local"
    assert response.routing.selected_model == "grok"
    assert response.fallback_used is True
