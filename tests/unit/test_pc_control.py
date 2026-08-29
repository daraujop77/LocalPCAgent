import subprocess
from unittest.mock import patch

import pytest

from integrations.pc.host import NativeWindowsPcControl, PcHostError
from integrations.pc.service import PcIntegration
from tests.support import make_permission_service


def _approved_invoke(pc, permissions, action, *, target=None, parameters=None):
    pending = pc.invoke(action, target=target, parameters=parameters)
    approval_id = pending.data["permission"]["approval"]["approval_id"]
    permissions.decide(approval_id, "accepted")
    approved_parameters = dict(parameters or {})
    approved_parameters["approval_id"] = approval_id
    return pc.invoke(action, target=target, parameters=approved_parameters)


def test_pc_file_operations_are_workspace_bounded(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"before\n")
    permissions = make_permission_service()
    pc = PcIntegration(permissions, workspace_root=str(tmp_path))

    read_result = pc.invoke("pc.files.read", target="source.txt")
    assert read_result.success is True
    assert read_result.data["content"] == "before\n"

    copy_result = pc.invoke(
        "pc.files.copy",
        target="source.txt",
        parameters={"destination": "working/copy.txt"},
    )
    assert copy_result.success is True
    assert (tmp_path / "working/copy.txt").read_text(encoding="utf-8") == "before\n"

    patch_result = _approved_invoke(
        pc,
        permissions,
        "pc.files.patch",
        target="working/copy.txt",
        parameters={"replacements": [{"old": "before", "new": "after"}]},
    )
    assert patch_result.success is True
    assert (tmp_path / "working/copy.txt").read_text(encoding="utf-8") == "after\n"

    outside_result = pc.invoke("pc.files.read", target=str(tmp_path.parent / "outside.txt"))
    assert outside_result.success is False
    assert outside_result.error == "path_outside_workspace"


def test_pc_mutations_require_explicit_approval() -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.calls = []

        def health(self):
            return NativeWindowsPcControl().health()

        def execute(self, action, *, target=None, parameters=None):
            self.calls.append((action, target, parameters))
            raise AssertionError("the backend should not run without approval")

    backend = RecordingBackend()
    pc = PcIntegration(make_permission_service(), backend=backend)

    result = pc.invoke("pc.input.type", parameters={"text": "blocked"})

    assert result.success is False
    assert result.error == "approval_required"
    assert backend.calls == []


def test_pc_powershell_policy_rejects_chaining_before_execution(tmp_path) -> None:
    permissions = make_permission_service()
    pc = PcIntegration(permissions, workspace_root=str(tmp_path))

    result = _approved_invoke(
        pc,
        permissions,
        "pc.shell.powershell",
        parameters={"verb": "Get-Date", "args": ["-Date", "today; Get-Date"]},
    )

    assert result.success is False
    assert result.error == "powershell_argument_not_allowlisted"


def test_pc_powershell_rejects_home_expansion_and_resolves_path_arguments(tmp_path) -> None:
    backend = NativeWindowsPcControl(workspace_root=tmp_path)

    with pytest.raises(PcHostError, match="powershell_path_not_allowlisted"):
        backend._parse_powershell_command(
            {"verb": "Set-Content", "args": ["-Path", "~\\outside.txt", "-Value", "x"]}
        )

    with pytest.raises(PcHostError, match="powershell_path_not_allowlisted"):
        backend._parse_powershell_command(
            {"verb": "Set-Content", "args": ["-Path", "..\\outside.txt", "-Value", "x"]}
        )


def test_pc_application_launch_uses_resolved_allowlisted_executable(tmp_path) -> None:
    backend = NativeWindowsPcControl(workspace_root=tmp_path, allowed_applications=("notepad.exe",))
    trusted = tmp_path / "trusted" / "notepad.exe"
    backend.allowed_application_paths = {"notepad.exe": trusted}
    process = type("Process", (), {"pid": 123})()

    with patch("integrations.pc.host.subprocess.Popen", return_value=process) as popen:
        result = backend.execute(
            "pc.apps.launch",
            parameters={"executable": "notepad.exe"},
        )

    assert result.success is True
    assert popen.call_args.args[0][0] == str(trusted)

    rejected = backend.execute(
        "pc.apps.launch",
        parameters={"executable": str(tmp_path / "untrusted" / "notepad.exe")},
    )
    assert rejected.error == "application_not_allowlisted"


def test_pc_subprocess_timeout_returns_structured_failure() -> None:
    backend = NativeWindowsPcControl()
    with patch.object(
        backend,
        "_powershell",
        side_effect=subprocess.TimeoutExpired("powershell", 1),
    ):
        result = backend.execute(
            "pc.shell.powershell",
            parameters={"verb": "Get-Date", "args": []},
        )

    assert result.success is False
    assert result.error == "pc_operation_timeout"


def test_pc_exposes_m3_capabilities() -> None:
    pc = PcIntegration(make_permission_service())

    assert "pc.apps.launch" in pc.capabilities()
    assert "pc.files.snapshot" in pc.capabilities()
    assert "pc.screen.capture" in pc.capabilities()
    assert "pc.input.hotkey" in pc.capabilities()


def test_legacy_approval_boolean_cannot_bypass_policy() -> None:
    backend_calls = []

    class Backend:
        def health(self):
            return NativeWindowsPcControl().health()

        def execute(self, action, *, target=None, parameters=None):
            backend_calls.append((action, target, parameters))
            raise AssertionError("legacy approval must not execute")

    pc = PcIntegration(make_permission_service(), backend=Backend())
    result = pc.invoke(
        "pc.input.type",
        parameters={"text": "blocked", "approval_granted": True},
    )

    assert result.error == "approval_required"
    assert backend_calls == []
