import subprocess
import sys

from personal_ai.contracts import CodingTask
from services.codex.service import CodexHandoffService, coding_task_from_payload
from tests.support import FakeCodexBackend, make_permission_service


def _git_repo(tmp_path):
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "fixture"], check=True, capture_output=True
    )
    return repo


def test_codex_handoff_requires_approval_without_starting_backend(tmp_path) -> None:
    repo = _git_repo(tmp_path)
    backend = FakeCodexBackend()
    service = CodexHandoffService(backend, make_permission_service())

    result = service.delegate(
        CodingTask(task_id="approval-test", repository_path=str(repo), task="change the fixture"),
    )

    assert result.success is False
    assert result.error == "approval_required"
    assert backend.calls == []
    assert service.list_runs()[0]["task_id"] == "approval-test"


def test_codex_handoff_observes_changes_and_runs_tests(tmp_path) -> None:
    repo = _git_repo(tmp_path)
    (repo / "preexisting.txt").write_text("user change\n", encoding="utf-8")
    permissions = make_permission_service()
    service = CodexHandoffService(FakeCodexBackend(), permissions)
    test_command = (
        sys.executable,
        "-c",
        "from pathlib import Path; assert Path('codex-handoff.txt').read_text() == 'changed by fake Codex\\n'",
    )

    task = CodingTask(
        task_id="fixture-change",
        repository_path=str(repo),
        task="write the fixture marker",
        test_command=test_command,
    )
    pending = service.delegate(task)
    approval_id = pending.approval["approval_id"]
    permissions.decide(approval_id, "accepted")

    result = service.delegate(task, approval_id=approval_id)

    assert result.success is True
    assert result.error is None
    assert result.changed_files == ("codex-handoff.txt",)
    assert result.preexisting_files == ("preexisting.txt",)
    assert len(result.tests) == 1
    assert result.tests[0].success is True
    assert result.starting_revision != result.ending_revision or result.starting_revision
    assert "Post-handoff tests passed" in result.summary


def test_legacy_boolean_cannot_bypass_codex_permission(tmp_path) -> None:
    repo = _git_repo(tmp_path)
    backend = FakeCodexBackend()
    service = CodexHandoffService(backend, make_permission_service())

    task, approval_id = coding_task_from_payload(
        {
            "task_id": "legacy",
            "repository_path": str(repo),
            "task": "do not run",
            "approval_granted": True,
        }
    )
    result = service.delegate(task, approval_id=approval_id)

    assert result.error == "approval_required"
    assert backend.calls == []
