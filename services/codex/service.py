"""Observable, non-interactive Codex handoff service."""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from personal_ai.contracts import (
    ApprovalLevel,
    CodexHandoffResult,
    CodingTask,
    HealthStatus,
    TestRun,
)
from personal_ai.permissions import PermissionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CodexBackendResult:
    """Provider-level result before repository diff and test observation."""

    success: bool
    summary: str
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None


class CodexBackend(Protocol):
    """Interface for a real or fake Codex execution backend."""

    def health(self) -> HealthStatus:
        """Return whether the backend can accept a handoff."""

    def run(self, task: CodingTask) -> CodexBackendResult:
        """Run the coding task in the task's repository without committing it."""


class SubprocessCodexBackend:
    """Invoke the installed Codex CLI with a bounded writable workspace."""

    def __init__(self, executable: str = "codex", timeout_seconds: float = 900.0) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def health(self) -> HealthStatus:
        resolved = shutil.which(self.executable)
        return HealthStatus(
            name="codex",
            status="ok" if resolved else "unavailable",
            ready=resolved is not None,
            details={
                "backend": "codex_cli",
                "executable": resolved or self.executable,
                "available": resolved is not None,
            },
        )

    def run(self, task: CodingTask) -> CodexBackendResult:
        prompt = self._prompt(task)
        command = [
            self.executable,
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "workspace-write",
            "-C",
            task.repository_path,
            prompt,
        ]
        logger.info(
            "codex_handoff_started",
            extra={"task_id": task.task_id, "repository_path": task.repository_path},
        )
        try:
            completed = subprocess.run(
                command,
                cwd=task.repository_path,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return CodexBackendResult(
                success=False,
                summary="Codex did not finish before the configured timeout.",
                error="codex_timeout",
            )
        except OSError as exc:
            return CodexBackendResult(
                success=False,
                summary="Codex could not be started.",
                warnings=(str(exc),),
                error="codex_unavailable",
            )

        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        summary = self._summarize_output(output)
        if completed.returncode != 0:
            return CodexBackendResult(
                success=False,
                summary=summary or "Codex returned a non-zero exit code.",
                logs=(f"codex_return_code={completed.returncode}",),
                error="codex_failed",
            )
        return CodexBackendResult(
            success=True,
            summary=summary or "Codex completed without a textual summary.",
            logs=("codex_exec_completed",),
        )

    @staticmethod
    def _prompt(task: CodingTask) -> str:
        constraints = "\n".join(f"- {constraint}" for constraint in task.constraints)
        return (
            "Perform the following repository coding task. Work only inside the supplied repository. "
            "Do not commit or push changes; the caller will inspect the working tree.\n\n"
            f"Task ID: {task.task_id}\n"
            f"Repository: {task.repository_path}\n"
            f"Task: {task.task}\n"
            f"Constraints:\n{constraints or '- Preserve existing behavior unless the task requires a change.'}\n"
            "Return a concise summary of changes and tests performed."
        )

    @staticmethod
    def _summarize_output(output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return ""
        return " ".join(lines[-8:])[-4000:]


@dataclass(slots=True)
class CodexHandoffService:
    """Validate, delegate, test, and record a repository coding handoff."""

    backend: CodexBackend
    permissions: PermissionService
    _runs: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        if self._runs is None:
            self._runs = []

    def health(self) -> HealthStatus:
        return self.backend.health()

    def list_runs(self) -> list[dict[str, object]]:
        return list(self._runs or [])

    def delegate(self, task: CodingTask, *, approval_id: str | None = None) -> CodexHandoffResult:
        started = perf_counter()
        action_policy = self.permissions.policy_for("codex.repository_handoff")
        if action_policy is None:
            raise RuntimeError("codex.repository_handoff is missing from the permission policy")
        task_id = task.task_id or uuid4().hex
        repository = Path(task.repository_path).expanduser().resolve()
        task = replace(task, task_id=task_id, repository_path=str(repository))

        validation_error = self._validate_repository(repository)
        if validation_error:
            return self._record(
                self._failure(
                    task,
                    started,
                    error=validation_error,
                    summary="Codex handoff rejected before execution.",
                    approval_level=action_policy.level,
                )
            )

        starting_revision = self._git_revision(repository)
        if (
            task.starting_revision
            and starting_revision
            and not starting_revision.startswith(task.starting_revision)
        ):
            return self._record(
                self._failure(
                    task,
                    started,
                    starting_revision=starting_revision,
                    error="starting_revision_mismatch",
                    summary="Codex handoff rejected because the repository revision changed.",
                    approval_level=action_policy.level,
                )
            )
        decision = self.permissions.authorize(
            "codex.repository_handoff",
            target=str(repository),
            parameters=self._permission_parameters(task),
            approval_id=approval_id,
        )
        if not decision.allowed:
            return self._record(
                self._failure(
                    task,
                    started,
                    starting_revision=starting_revision,
                    error=decision.error or "permission_denied",
                    summary="Repository handoff was not authorized by the M4 permission policy.",
                    warnings=("No Codex process was started.",),
                    approval_level=decision.level,
                    approval=decision.approval.to_dict() if decision.approval else None,
                )
            )

        try:
            backend_result = self.backend.run(task)
        except Exception as exc:  # noqa: BLE001 - provider failures must stay structured
            logger.exception("codex_handoff_failed", extra={"task_id": task.task_id})
            backend_result = CodexBackendResult(
                success=False,
                summary="The Codex backend failed unexpectedly.",
                warnings=(str(exc),),
                error="codex_backend_failed",
            )
        ending_revision = self._git_revision(repository)
        changed_files = self._changed_files(repository)
        tests = self._run_tests(task, repository) if backend_result.success else ()
        tests_failed = any(not test.success for test in tests)
        success = backend_result.success and not tests_failed
        error = backend_result.error
        if tests_failed:
            error = "tests_failed"
        warnings = list(backend_result.warnings)
        if tests and not tests_failed:
            summary = f"{backend_result.summary} Post-handoff tests passed."
        elif tests_failed:
            summary = f"{backend_result.summary} Post-handoff tests failed."
        else:
            summary = backend_result.summary
        result = CodexHandoffResult(
            success=success,
            task_id=task.task_id,
            repository_path=task.repository_path,
            starting_revision=starting_revision,
            ending_revision=ending_revision,
            summary=summary,
            changed_files=changed_files,
            tests=tests,
            logs=backend_result.logs + (f"changed_files={len(changed_files)}",),
            warnings=tuple(warnings),
            error=error,
            approval_level=decision.level,
            approval=decision.approval.to_dict() if decision.approval else None,
            duration_ms=self._duration_ms(started),
        )
        logger.info(
            "codex_handoff_completed",
            extra={
                "task_id": task.task_id,
                "success": result.success,
                "changed_files": list(result.changed_files),
                "error": result.error,
                "duration_ms": result.duration_ms,
            },
        )
        return self._record(result)

    @staticmethod
    def _permission_parameters(task: CodingTask) -> dict[str, object]:
        return {
            "task": task.task,
            "starting_revision": task.starting_revision,
            "constraints": list(task.constraints),
            "test_command": list(task.test_command),
            "test_timeout_seconds": task.test_timeout_seconds,
        }

    @staticmethod
    def _validate_repository(repository: Path) -> str | None:
        if not repository.is_dir():
            return "repository_not_found"
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            return "repository_not_git"
        try:
            git_root = Path(completed.stdout.strip()).resolve()
        except OSError:
            return "repository_not_git"
        return None if git_root == repository else "repository_path_must_be_git_root"

    @staticmethod
    def _git_revision(repository: Path) -> str | None:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        revision = completed.stdout.strip()
        return revision if completed.returncode == 0 and revision else None

    @staticmethod
    def _changed_files(repository: Path) -> tuple[str, ...]:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        changed: set[str] = set()
        for line in completed.stdout.splitlines():
            if len(line) >= 4:
                changed.add(line[3:].strip().strip('"'))
        return tuple(sorted(changed))

    @classmethod
    def _run_tests(cls, task: CodingTask, repository: Path) -> tuple[TestRun, ...]:
        if not task.test_command:
            return ()
        started = perf_counter()
        try:
            completed = subprocess.run(
                list(task.test_command),
                cwd=repository,
                capture_output=True,
                text=True,
                timeout=task.test_timeout_seconds,
                check=False,
                shell=False,
            )
            output = "\n".join(
                part for part in (completed.stdout, completed.stderr) if part
            ).strip()[-8000:]
            return (
                TestRun(
                    command=task.test_command,
                    success=completed.returncode == 0,
                    return_code=completed.returncode,
                    output=output,
                    duration_ms=cls._duration_ms(started),
                ),
            )
        except subprocess.TimeoutExpired as exc:
            output = str(exc).strip()[-8000:]
            return (
                TestRun(
                    command=task.test_command,
                    success=False,
                    return_code=None,
                    output=output,
                    duration_ms=cls._duration_ms(started),
                ),
            )
        except OSError as exc:
            return (
                TestRun(
                    command=task.test_command,
                    success=False,
                    return_code=None,
                    output=str(exc),
                    duration_ms=cls._duration_ms(started),
                ),
            )

    @staticmethod
    def _failure(
        task: CodingTask,
        started: float,
        *,
        error: str,
        summary: str,
        starting_revision: str | None = None,
        warnings: tuple[str, ...] = (),
        approval_level: ApprovalLevel = 2,
        approval: Mapping[str, object] | None = None,
    ) -> CodexHandoffResult:
        return CodexHandoffResult(
            success=False,
            task_id=task.task_id,
            repository_path=task.repository_path,
            starting_revision=starting_revision,
            ending_revision=starting_revision,
            summary=summary,
            warnings=warnings,
            error=error,
            approval_level=approval_level,
            approval=approval,
            duration_ms=CodexHandoffService._duration_ms(started),
        )

    def _record(self, result: CodexHandoffResult) -> CodexHandoffResult:
        self._runs.append(result.to_dict())
        return result

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))


class CodingTaskValidationError(ValueError):
    """Raised when an HTTP handoff payload is not safe to execute."""


def coding_task_from_payload(payload: object) -> tuple[CodingTask, str | None]:
    """Parse the gateway request while keeping commands as argv, never shell text."""

    if not isinstance(payload, Mapping):
        raise CodingTaskValidationError("request body must be a JSON object")
    repository_path = payload.get("repository_path")
    task_text = payload.get("task")
    if not isinstance(repository_path, str) or not repository_path.strip():
        raise CodingTaskValidationError("repository_path must be a non-empty string")
    if not isinstance(task_text, str) or not task_text.strip():
        raise CodingTaskValidationError("task must be a non-empty string")

    task_id = payload.get("task_id", "")
    if not isinstance(task_id, str):
        raise CodingTaskValidationError("task_id must be a string when provided")
    starting_revision = payload.get("starting_revision")
    if starting_revision is not None and not isinstance(starting_revision, str):
        raise CodingTaskValidationError("starting_revision must be a string when provided")
    constraints = _string_tuple(payload.get("constraints", ()), "constraints")
    test_command = _string_tuple(payload.get("test_command", ()), "test_command")
    timeout = payload.get("test_timeout_seconds", 120.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise CodingTaskValidationError("test_timeout_seconds must be greater than zero")
    approval_id = payload.get("approval_id")
    if approval_id is not None and not isinstance(approval_id, str):
        raise CodingTaskValidationError("approval_id must be a string when provided")
    return (
        CodingTask(
            task_id=task_id.strip(),
            repository_path=repository_path.strip(),
            task=task_text.strip(),
            starting_revision=starting_revision.strip() if starting_revision else None,
            constraints=constraints,
            test_command=test_command,
            test_timeout_seconds=float(timeout),
        ),
        approval_id.strip() if approval_id else None,
    )


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise CodingTaskValidationError(f"{name} must be an array of strings")
    if not all(isinstance(item, str) and item for item in value):
        raise CodingTaskValidationError(f"{name} must contain only non-empty strings")
    return tuple(value)
