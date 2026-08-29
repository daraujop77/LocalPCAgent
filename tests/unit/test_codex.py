import subprocess
import sys

from personal_ai.contracts import CodingTask
from services.codex.service import CodexHandoffService
from tests.support import FakeCodexBackend


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
    service = CodexHandoffService(backend)

    result = service.delegate(
        CodingTask(task_id="approval-test", repository_path=str(repo), task="change the fixture"),
    )

    assert result.success is False
    assert result.error == "approval_required"
    assert backend.calls == []
    assert service.list_runs()[0]["task_id"] == "approval-test"


def test_codex_handoff_observes_changes_and_runs_tests(tmp_path) -> None:
    repo = _git_repo(tmp_path)
    service = CodexHandoffService(FakeCodexBackend())
    test_command = (
        sys.executable,
        "-c",
        "from pathlib import Path; assert Path('codex-handoff.txt').read_text() == 'changed by fake Codex\\n'",
    )

    result = service.delegate(
        CodingTask(
            task_id="fixture-change",
            repository_path=str(repo),
            task="write the fixture marker",
            test_command=test_command,
        ),
        approval_granted=True,
    )

    assert result.success is True
    assert result.error is None
    assert result.changed_files == ("codex-handoff.txt",)
    assert len(result.tests) == 1
    assert result.tests[0].success is True
    assert result.starting_revision != result.ending_revision or result.starting_revision
    assert "Post-handoff tests passed" in result.summary
