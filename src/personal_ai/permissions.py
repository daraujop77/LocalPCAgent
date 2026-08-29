"""Validated M4 permission policy, scoped approvals, and audit records."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Literal, cast
from uuid import uuid4

from personal_ai.contracts import ApprovalLevel, HealthStatus

logger = logging.getLogger(__name__)

ApprovalStatus = Literal["requested", "accepted", "rejected", "expired", "cancelled"]
DecisionStatus = Literal["accepted", "rejected", "cancelled"]


class PermissionServiceError(ValueError):
    """Stable validation or lifecycle error returned by the permission API."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LevelPolicy:
    level: ApprovalLevel
    name: str
    automatic: bool


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    action: str
    level: ApprovalLevel
    privileged: bool = False


@dataclass(frozen=True, slots=True)
class PcAllowlist:
    applications: tuple[str, ...]
    powershell_verbs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrivilegedHelperPolicy:
    enabled: bool
    transport: str
    endpoint: str
    allowed_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    """Immutable validated policy loaded from the checked-in JSON-compatible YAML."""

    source: str
    version: int
    approval_ttl_seconds: int
    levels: Mapping[ApprovalLevel, LevelPolicy]
    actions: Mapping[str, ActionPolicy]
    pc: PcAllowlist
    main_process_administrator_required: bool
    privileged_helper: PrivilegedHelperPolicy

    @classmethod
    def load(cls, path: str | Path) -> PermissionPolicy:
        resolved = Path(path).expanduser().resolve()
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PermissionServiceError("policy_not_found", str(resolved)) from exc
        except json.JSONDecodeError as exc:
            raise PermissionServiceError("policy_invalid_json", str(exc)) from exc
        if not isinstance(payload, Mapping):
            raise PermissionServiceError("policy_root_must_be_object")
        return cls._from_payload(payload, source=str(resolved))

    @classmethod
    def _from_payload(cls, payload: Mapping[str, object], *, source: str) -> PermissionPolicy:
        version = payload.get("version")
        if version != 1:
            raise PermissionServiceError("policy_version_unsupported")
        ttl = payload.get("approval_ttl_seconds")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= 86400:
            raise PermissionServiceError("approval_ttl_invalid")

        raw_levels = _mapping(payload.get("levels"), "levels")
        levels: dict[ApprovalLevel, LevelPolicy] = {}
        for raw_level, expected_automatic in ((0, True), (1, True), (2, False), (3, False)):
            value = _mapping(raw_levels.get(str(raw_level)), f"levels.{raw_level}")
            name = _non_empty_string(value.get("name"), f"levels.{raw_level}.name")
            automatic = value.get("automatic")
            if automatic is not expected_automatic:
                raise PermissionServiceError("permission_level_automatic_invalid")
            level = cast(ApprovalLevel, raw_level)
            levels[level] = LevelPolicy(level=level, name=name, automatic=automatic)
        if set(raw_levels) != {"0", "1", "2", "3"}:
            raise PermissionServiceError("permission_levels_must_be_exact")

        raw_actions = _mapping(payload.get("actions"), "actions")
        actions: dict[str, ActionPolicy] = {}
        for raw_action, raw_policy in raw_actions.items():
            action = _non_empty_string(raw_action, "actions key")
            if action in actions:
                raise PermissionServiceError("duplicate_action_policy")
            value = _mapping(raw_policy, f"actions.{action}")
            raw_level = value.get("level")
            if (
                isinstance(raw_level, bool)
                or not isinstance(raw_level, int)
                or raw_level not in levels
            ):
                raise PermissionServiceError("action_level_invalid", action)
            privileged = value.get("privileged", False)
            if not isinstance(privileged, bool):
                raise PermissionServiceError("action_privileged_invalid", action)
            if privileged and raw_level != 3:
                raise PermissionServiceError("privileged_action_must_be_level_3", action)
            level = cast(ApprovalLevel, raw_level)
            actions[action] = ActionPolicy(action=action, level=level, privileged=privileged)
        if not actions:
            raise PermissionServiceError("actions_must_not_be_empty")

        raw_pc = _mapping(payload.get("pc"), "pc")
        applications = _unique_strings(raw_pc.get("allowed_applications"), "allowed_applications")
        for application in applications:
            if Path(application).name != application or not application.lower().endswith(".exe"):
                raise PermissionServiceError("allowed_application_invalid", application)
        powershell_verbs = _unique_strings(
            raw_pc.get("allowed_powershell_verbs"),
            "allowed_powershell_verbs",
        )
        if any(re.fullmatch(r"[A-Za-z]+-[A-Za-z]+", verb) is None for verb in powershell_verbs):
            raise PermissionServiceError("allowed_powershell_verb_invalid")

        raw_main = _mapping(payload.get("main_process"), "main_process")
        administrator_required = raw_main.get("administrator_required")
        if administrator_required is not False:
            raise PermissionServiceError("main_process_must_not_require_administrator")

        raw_helper = _mapping(payload.get("privileged_helper"), "privileged_helper")
        helper_enabled = raw_helper.get("enabled")
        if not isinstance(helper_enabled, bool):
            raise PermissionServiceError("privileged_helper_enabled_invalid")
        helper_transport = _non_empty_string(raw_helper.get("transport"), "helper transport")
        helper_endpoint = _non_empty_string(raw_helper.get("endpoint"), "helper endpoint")
        helper_actions = _unique_strings(raw_helper.get("allowed_actions"), "helper actions")
        for action in helper_actions:
            action_policy = actions.get(action)
            if action_policy is None or not action_policy.privileged:
                raise PermissionServiceError("helper_action_not_privileged", action)

        return cls(
            source=source,
            version=version,
            approval_ttl_seconds=ttl,
            levels=levels,
            actions=actions,
            pc=PcAllowlist(
                applications=applications,
                powershell_verbs=powershell_verbs,
            ),
            main_process_administrator_required=administrator_required,
            privileged_helper=PrivilegedHelperPolicy(
                enabled=helper_enabled,
                transport=helper_transport,
                endpoint=helper_endpoint,
                allowed_actions=helper_actions,
            ),
        )

    def summary(self) -> dict[str, object]:
        return {
            "source": self.source,
            "version": self.version,
            "approval_ttl_seconds": self.approval_ttl_seconds,
            "levels": {
                str(level): {"name": item.name, "automatic": item.automatic}
                for level, item in self.levels.items()
            },
            "actions": {
                name: {"level": item.level, "privileged": item.privileged}
                for name, item in self.actions.items()
            },
            "pc": {
                "allowed_applications": list(self.pc.applications),
                "allowed_powershell_verbs": list(self.pc.powershell_verbs),
            },
            "main_process": {
                "administrator_required": self.main_process_administrator_required,
            },
            "privileged_helper": {
                "enabled": self.privileged_helper.enabled,
                "transport": self.privileged_helper.transport,
                "endpoint": self.privileged_helper.endpoint,
                "allowed_actions": list(self.privileged_helper.allowed_actions),
            },
        }


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    action: str
    target: str | None
    level: ApprovalLevel
    status: ApprovalStatus
    scope_digest: str
    reason: str
    requested_by: str
    requested_at: str
    expires_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    consumed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "action": self.action,
            "target": self.target,
            "level": self.level,
            "status": self.status,
            "scope_digest": self.scope_digest,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "consumed_at": self.consumed_at,
        }


@dataclass(frozen=True, slots=True)
class PermissionEvent:
    event_id: str
    event_type: str
    timestamp: str
    approval_id: str | None
    action: str
    details: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "approval_id": self.approval_id,
            "action": self.action,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    action: str
    level: ApprovalLevel
    automatic: bool
    error: str | None = None
    approval: ApprovalRequest | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "level": self.level,
            "automatic": self.automatic,
            "error": self.error,
            "approval": self.approval.to_dict() if self.approval else None,
        }


class PermissionService:
    """Thread-safe process-local approval store and fail-closed policy evaluator."""

    def __init__(
        self,
        policy: PermissionPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))
        self._requests: dict[str, ApprovalRequest] = {}
        self._events: list[PermissionEvent] = []
        self._lock = RLock()

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> PermissionService:
        return cls(PermissionPolicy.load(path), clock=clock)

    def health(self) -> HealthStatus:
        return HealthStatus(
            name="permissions",
            status="ok",
            ready=True,
            details={
                "policy_version": self.policy.version,
                "policy_source": self.policy.source,
                "approval_store": "process_local",
                "requests": len(self._requests),
                "privileged_helper_enabled": self.policy.privileged_helper.enabled,
                "fail_closed": True,
            },
        )

    def policy_for(self, action: str) -> ActionPolicy | None:
        return self.policy.actions.get(action)

    def request_approval(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
        reason: str = "Action requires explicit approval.",
        requested_by: str = "gateway",
    ) -> ApprovalRequest:
        action_policy = self.policy_for(action)
        if action_policy is None:
            raise PermissionServiceError("unsupported_action", action)
        if self.policy.levels[action_policy.level].automatic:
            raise PermissionServiceError("approval_not_required", action)
        now = self._now()
        request = ApprovalRequest(
            approval_id=uuid4().hex,
            action=action,
            target=target,
            level=action_policy.level,
            status="requested",
            scope_digest=self.scope_digest(action, target=target, parameters=parameters),
            reason=reason,
            requested_by=requested_by,
            requested_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.policy.approval_ttl_seconds)).isoformat(),
        )
        with self._lock:
            self._requests[request.approval_id] = request
            self._emit("approval.requested", request, {"reason": reason})
        logger.info(
            "approval_requested",
            extra={
                "approval_id": request.approval_id,
                "action": action,
                "target": target,
                "level": action_policy.level,
            },
        )
        return request

    def decide(
        self,
        approval_id: str,
        status: DecisionStatus,
        *,
        decided_by: str = "user",
        reason: str | None = None,
    ) -> ApprovalRequest:
        if status not in {"accepted", "rejected", "cancelled"}:
            raise PermissionServiceError("approval_decision_invalid")
        with self._lock:
            request = self._get_and_refresh(approval_id)
            if request.status != "requested":
                raise PermissionServiceError(
                    "approval_transition_invalid",
                    f"cannot change approval from {request.status} to {status}",
                )
            updated = replace(
                request,
                status=status,
                decided_at=self._now().isoformat(),
                decided_by=decided_by,
                decision_reason=reason,
            )
            self._requests[approval_id] = updated
            self._emit(f"approval.{status}", updated, {"reason": reason or ""})
        logger.info(
            "approval_decided",
            extra={"approval_id": approval_id, "action": updated.action, "status": status},
        )
        return updated

    def authorize(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
        approval_id: str | None = None,
        requested_by: str = "gateway",
    ) -> PermissionDecision:
        action_policy = self.policy_for(action)
        if action_policy is None:
            return PermissionDecision(
                allowed=False,
                action=action,
                level=0,
                automatic=False,
                error="unsupported_action",
            )
        level_policy = self.policy.levels[action_policy.level]
        if level_policy.automatic:
            self._emit_permission("permission.allowed", action, None, {"automatic": True})
            return PermissionDecision(
                allowed=True,
                action=action,
                level=action_policy.level,
                automatic=True,
            )

        if not approval_id:
            request = self.request_approval(
                action,
                target=target,
                parameters=parameters,
                requested_by=requested_by,
            )
            return PermissionDecision(
                allowed=False,
                action=action,
                level=action_policy.level,
                automatic=False,
                error="approval_required",
                approval=request,
            )

        with self._lock:
            try:
                request = self._get_and_refresh(approval_id)
            except PermissionServiceError as exc:
                return PermissionDecision(
                    allowed=False,
                    action=action,
                    level=action_policy.level,
                    automatic=False,
                    error=exc.code,
                )
            expected_digest = self.scope_digest(action, target=target, parameters=parameters)
            if (
                request.action != action
                or request.target != target
                or request.level != action_policy.level
                or request.scope_digest != expected_digest
            ):
                self._emit_permission(
                    "permission.denied",
                    action,
                    request.approval_id,
                    {"error": "approval_scope_mismatch"},
                )
                return PermissionDecision(
                    allowed=False,
                    action=action,
                    level=action_policy.level,
                    automatic=False,
                    error="approval_scope_mismatch",
                    approval=request,
                )
            if request.status != "accepted":
                error = f"approval_{request.status}"
                return PermissionDecision(
                    allowed=False,
                    action=action,
                    level=action_policy.level,
                    automatic=False,
                    error=error,
                    approval=request,
                )
            if request.consumed_at is not None:
                return PermissionDecision(
                    allowed=False,
                    action=action,
                    level=action_policy.level,
                    automatic=False,
                    error="approval_already_used",
                    approval=request,
                )
            if action_policy.privileged:
                helper = self.policy.privileged_helper
                if not helper.enabled:
                    return PermissionDecision(
                        allowed=False,
                        action=action,
                        level=action_policy.level,
                        automatic=False,
                        error="privileged_helper_unavailable",
                        approval=request,
                    )
                if action not in helper.allowed_actions:
                    return PermissionDecision(
                        allowed=False,
                        action=action,
                        level=action_policy.level,
                        automatic=False,
                        error="privileged_action_not_allowlisted",
                        approval=request,
                    )

            consumed = replace(request, consumed_at=self._now().isoformat())
            self._requests[approval_id] = consumed
            self._emit("approval.consumed", consumed, {})
            self._emit_permission(
                "permission.allowed",
                action,
                approval_id,
                {"automatic": False},
            )
            return PermissionDecision(
                allowed=True,
                action=action,
                level=action_policy.level,
                automatic=False,
                approval=consumed,
            )

    def get(self, approval_id: str) -> ApprovalRequest:
        with self._lock:
            return self._get_and_refresh(approval_id)

    def list_requests(self, *, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        with self._lock:
            requests = [self._get_and_refresh(item) for item in list(self._requests)]
        if status is not None:
            requests = [request for request in requests if request.status == status]
        return sorted(requests, key=lambda item: item.requested_at, reverse=True)

    def events(self) -> list[PermissionEvent]:
        with self._lock:
            return list(self._events)

    @staticmethod
    def sanitized_parameters(
        parameters: Mapping[str, object] | None,
    ) -> dict[str, object]:
        return {
            key: value
            for key, value in dict(parameters or {}).items()
            if key not in {"approval_id", "approval_granted"}
        }

    @classmethod
    def scope_digest(
        cls,
        action: str,
        *,
        target: str | None,
        parameters: Mapping[str, object] | None,
    ) -> str:
        scope = {
            "action": action,
            "target": target,
            "parameters": cls.sanitized_parameters(parameters),
        }
        canonical = json.dumps(
            scope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _get_and_refresh(self, approval_id: str) -> ApprovalRequest:
        request = self._requests.get(approval_id)
        if request is None:
            raise PermissionServiceError("approval_not_found", approval_id)
        if (
            request.status in {"requested", "accepted"}
            and request.consumed_at is None
            and self._now() >= datetime.fromisoformat(request.expires_at)
        ):
            request = replace(request, status="expired", decided_at=self._now().isoformat())
            self._requests[approval_id] = request
            self._emit("approval.expired", request, {})
        return request

    def _emit(
        self,
        event_type: str,
        request: ApprovalRequest,
        details: Mapping[str, object],
    ) -> None:
        self._events.append(
            PermissionEvent(
                event_id=uuid4().hex,
                event_type=event_type,
                timestamp=self._now().isoformat(),
                approval_id=request.approval_id,
                action=request.action,
                details=dict(details),
            )
        )

    def _emit_permission(
        self,
        event_type: str,
        action: str,
        approval_id: str | None,
        details: Mapping[str, object],
    ) -> None:
        with self._lock:
            self._events.append(
                PermissionEvent(
                    event_id=uuid4().hex,
                    event_type=event_type,
                    timestamp=self._now().isoformat(),
                    approval_id=approval_id,
                    action=action,
                    details=dict(details),
                )
            )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now.astimezone(UTC)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PermissionServiceError("policy_field_must_be_object", name)
    if not all(isinstance(key, str) for key in value):
        raise PermissionServiceError("policy_object_keys_must_be_strings", name)
    return cast(Mapping[str, object], value)


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PermissionServiceError("policy_field_must_be_non_empty_string", name)
    return value.strip()


def _unique_strings(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PermissionServiceError("policy_field_must_be_string_array", name)
    items = tuple(_non_empty_string(item, name) for item in value)
    normalized = [item.casefold() for item in items]
    if len(set(normalized)) != len(items):
        raise PermissionServiceError("policy_string_array_has_duplicates", name)
    return items
