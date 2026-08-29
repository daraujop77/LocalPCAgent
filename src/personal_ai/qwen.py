"""OpenAI-compatible local Qwen client boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from personal_ai.chat import ChatMessage
from personal_ai.config import Settings
from personal_ai.contracts import HealthStatus


class ModelBackendError(RuntimeError):
    """Base error with a stable public error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ModelUnavailableError(ModelBackendError):
    """The configured local model endpoint could not be reached."""


class ModelProtocolError(ModelBackendError):
    """The endpoint responded but did not satisfy the expected protocol."""


@dataclass(frozen=True, slots=True)
class ModelReply:
    content: str
    model_name: str
    usage: Mapping[str, object] = field(default_factory=dict)


class ModelClient(Protocol):
    route_name: str
    model_name: str

    def health(self) -> HealthStatus:
        """Return local backend availability without generating text."""

    def complete(self, messages: Sequence[ChatMessage], *, request_id: str) -> ModelReply:
        """Generate one non-streaming assistant response."""


class HttpQwenClient:
    """Use a local OpenAI-compatible `/v1` endpoint without a runtime SDK dependency."""

    route_name = "qwen-local"

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.qwen_base_url.rstrip("/")
        self._model_name = settings.qwen_model
        self._timeout_seconds = settings.qwen_timeout_seconds
        self._health_timeout_seconds = settings.qwen_health_timeout_seconds
        self._api_key = settings.qwen_api_key

    @property
    def model_name(self) -> str:
        return self._model_name

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        timeout: float,
    ) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(
            f"{self._base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw_body = response.read()
        except HTTPError as exc:
            if exc.code >= 500:
                raise ModelUnavailableError("qwen_unavailable") from None
            raise ModelProtocolError("qwen_http_error") from None
        except (OSError, TimeoutError, URLError):
            raise ModelUnavailableError("qwen_unavailable") from None

        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ModelProtocolError("qwen_invalid_json") from None
        if not isinstance(parsed, dict):
            raise ModelProtocolError("qwen_invalid_response")
        return parsed

    def health(self) -> HealthStatus:
        details: dict[str, object] = {
            "backend": "openai_compatible_http",
            "base_url": self._base_url,
            "model": self._model_name,
        }
        try:
            self._request("GET", "models", timeout=self._health_timeout_seconds)
        except ModelBackendError as exc:
            details["error"] = exc.code
            return HealthStatus(name="qwen", status="unavailable", ready=False, details=details)
        return HealthStatus(name="qwen", status="ok", ready=True, details=details)

    def complete(self, messages: Sequence[ChatMessage], *, request_id: str) -> ModelReply:
        del request_id
        payload = {
            "model": self._model_name,
            "messages": [message.to_dict() for message in messages],
            "stream": False,
        }
        response = self._request(
            "POST",
            "chat/completions",
            payload=payload,
            timeout=self._timeout_seconds,
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelProtocolError("qwen_missing_choices")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelProtocolError("qwen_missing_content")
        usage = response.get("usage")
        return ModelReply(
            content=message["content"],
            model_name=response.get("model", self._model_name)
            if isinstance(response.get("model", self._model_name), str)
            else self._model_name,
            usage=usage if isinstance(usage, dict) else {},
        )
