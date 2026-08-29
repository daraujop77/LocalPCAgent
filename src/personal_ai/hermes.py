"""Hermes conversational boundary backed by the local Qwen client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from personal_ai.chat import ChatMessage, ChatRequest
from personal_ai.contracts import CodexHandoffResult, CodingTask, HealthStatus
from personal_ai.qwen import ModelBackendError, ModelClient
from personal_ai.router import ModelRouter, ModelSelection

logger = logging.getLogger(__name__)


class CodexDelegator(Protocol):
    """Explicit repository handoff boundary owned by the conversational layer."""

    def delegate(
        self,
        task: CodingTask,
        *,
        approval_id: str | None = None,
    ) -> CodexHandoffResult:
        """Delegate one already-validated coding task to Codex."""


@dataclass(frozen=True, slots=True)
class ChatResponse:
    success: bool
    request_id: str
    conversation_id: str
    message: ChatMessage | None
    model: str | None
    model_name: str | None
    routing: ModelSelection
    fallback_used: bool
    usage: dict[str, object] = field(default_factory=dict)
    latency_ms: int = 0
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        routing = self.routing.to_dict()
        routing["fallback_used"] = self.fallback_used
        return {
            "success": self.success,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "message": self.message.to_dict() if self.message else None,
            "model": self.model,
            "model_name": self.model_name,
            "routing": routing,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(slots=True)
class HermesService:
    """One-turn Hermes service; durable memory belongs to later milestones."""

    model_client: ModelClient
    router: ModelRouter
    codex: CodexDelegator | None = None

    def health(self) -> HealthStatus:
        backend = self.model_client.health()
        return HealthStatus(
            name="hermes",
            status="ok" if backend.ready else "degraded",
            ready=backend.ready,
            details={
                "agent": "hermes",
                "model_route": self.model_client.route_name,
                "backend": backend.to_dict(),
                "conversation_memory": "request_only",
            },
        )

    def chat(self, request: ChatRequest) -> ChatResponse:
        started = perf_counter()
        request_id = uuid4().hex
        conversation_id = request.conversation_id or uuid4().hex
        routing = self.router.select(request.task_type)
        logger.info(
            "model_selected",
            extra={
                "request_id": request_id,
                "task_type": routing.task_type,
                "selected_model": routing.selected_model,
                "reason": routing.reason,
                "fallback_model": routing.fallback_model,
            },
        )

        fallback_used = routing.selected_model != self.model_client.route_name
        if fallback_used and routing.fallback_model != self.model_client.route_name:
            return self._failure(
                request_id=request_id,
                conversation_id=conversation_id,
                routing=routing,
                fallback_used=False,
                started=started,
                error="model_unavailable",
                warnings=("The selected specialist is not configured in M1.",),
            )
        if fallback_used:
            logger.info(
                "model_fallback",
                extra={
                    "request_id": request_id,
                    "from_model": routing.selected_model,
                    "to_model": self.model_client.route_name,
                    "reason": "specialist_not_configured",
                },
            )

        try:
            reply = self.model_client.complete(request.messages(), request_id=request_id)
        except ModelBackendError as exc:
            logger.info(
                "model_failed",
                extra={
                    "request_id": request_id,
                    "selected_model": routing.selected_model,
                    "used_model": self.model_client.route_name,
                    "outcome": "failure",
                    "error": exc.code,
                },
            )
            return self._failure(
                request_id=request_id,
                conversation_id=conversation_id,
                routing=routing,
                fallback_used=fallback_used,
                started=started,
                error=exc.code,
                warnings=("Start or check the configured local Qwen server.",),
            )

        latency_ms = self._latency_ms(started)
        logger.info(
            "chat_completed",
            extra={
                "request_id": request_id,
                "selected_model": routing.selected_model,
                "used_model": self.model_client.route_name,
                "latency_ms": latency_ms,
                "outcome": "success",
            },
        )
        return ChatResponse(
            success=True,
            request_id=request_id,
            conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=reply.content),
            model=self.model_client.route_name,
            model_name=reply.model_name,
            routing=routing,
            fallback_used=fallback_used,
            usage=dict(reply.usage),
            latency_ms=latency_ms,
        )

    def delegate_to_codex(
        self,
        task: CodingTask,
        *,
        approval_id: str | None = None,
    ) -> CodexHandoffResult:
        """Route an explicit coding handoff through Hermes to the Codex boundary."""

        if self.codex is None:
            raise RuntimeError("Codex delegation is not configured")
        logger.info(
            "hermes_codex_handoff_requested",
            extra={"task_id": task.task_id, "repository_path": task.repository_path},
        )
        return self.codex.delegate(task, approval_id=approval_id)

    def _failure(
        self,
        *,
        request_id: str,
        conversation_id: str,
        routing: ModelSelection,
        fallback_used: bool,
        started: float,
        error: str,
        warnings: tuple[str, ...],
    ) -> ChatResponse:
        return ChatResponse(
            success=False,
            request_id=request_id,
            conversation_id=conversation_id,
            message=None,
            model=self.model_client.route_name if fallback_used else None,
            model_name=self.model_client.model_name if fallback_used else None,
            routing=routing,
            fallback_used=fallback_used,
            latency_ms=self._latency_ms(started),
            warnings=warnings,
            error=error,
        )

    @staticmethod
    def _latency_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))
