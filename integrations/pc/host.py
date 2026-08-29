"""Windows-native primitives behind the controlled PC integration."""

from __future__ import annotations

import csv
import ctypes
import logging
import os
import platform
import re
import shutil
import struct
import subprocess
from collections.abc import Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from personal_ai.contracts import HealthStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PcExecution:
    """Backend result that the provider wraps in the common ToolResult envelope."""

    success: bool
    summary: str
    data: Mapping[str, object] = field(default_factory=dict)
    changed_files: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None
    reversible: bool = True
    duration_ms: int | None = None


class PcControlBackend(Protocol):
    """Interface for native Windows control and deterministic test doubles."""

    def health(self) -> HealthStatus:
        """Return host-control readiness without changing host state."""

    def execute(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> PcExecution:
        """Execute one structured, policy-bounded operation."""


class PcHostError(RuntimeError):
    """Stable error for a rejected or unsupported host operation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NativeWindowsPcControl:
    """Implement the M3 primitives without a shell or administrator privileges."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        allowed_applications: Sequence[str] = ("notepad.exe", "calc.exe", "mspaint.exe"),
        command_timeout_seconds: float = 30.0,
    ) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).expanduser().resolve()
        self.allowed_applications = frozenset(
            Path(name).name.lower() for name in allowed_applications
        )
        self.command_timeout_seconds = command_timeout_seconds

    def health(self) -> HealthStatus:
        supported = os.name == "nt"
        return HealthStatus(
            name="pc",
            status="ok" if supported else "unsupported_platform",
            ready=supported,
            details={
                "mode": "controlled_native_windows",
                "control_enabled": supported,
                "administrator_required": False,
                "workspace_root": str(self.workspace_root),
                "allowed_applications": sorted(self.allowed_applications),
            },
        )

    def execute(
        self,
        action: str,
        *,
        target: str | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> PcExecution:
        started = perf_counter()
        params = parameters or {}
        handlers = {
            "pc.system_info": self._system_info,
            "pc.list_processes": self._list_processes,
            "pc.apps.list": self._apps_list,
            "pc.apps.launch": self._apps_launch,
            "pc.apps.focus": self._window_focus,
            "pc.apps.close": self._apps_close,
            "pc.files.read": self._files_read,
            "pc.files.copy": self._files_copy,
            "pc.files.move": self._files_move,
            "pc.files.patch": self._files_patch,
            "pc.files.snapshot": self._files_snapshot,
            "pc.shell.powershell": self._powershell,
            "pc.window.list": self._window_list,
            "pc.window.focus": self._window_focus,
            "pc.screen.capture": self._screen_capture,
            "pc.input.click": self._input_click,
            "pc.input.drag": self._input_drag,
            "pc.input.type": self._input_type,
            "pc.input.hotkey": self._input_hotkey,
            "pc.input.scroll": self._input_scroll,
        }
        handler = handlers.get(action)
        if handler is None:
            return PcExecution(
                success=False,
                summary=f"Unsupported PC action: {action}.",
                error="unsupported_action",
                duration_ms=self._duration_ms(started),
            )
        logger.info("pc_operation_started", extra={"action": action, "target": target})
        try:
            result = handler(target, params)
        except PcHostError as exc:
            result = PcExecution(
                success=False,
                summary=f"PC operation rejected: {exc.code}.",
                error=exc.code,
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.exception("pc_operation_failed", extra={"action": action})
            result = PcExecution(
                success=False,
                summary="PC operation failed.",
                warnings=(str(exc),),
                error="pc_operation_failed",
            )
        result = replace(result, duration_ms=self._duration_ms(started))
        logger.info(
            "pc_operation_completed",
            extra={
                "action": action,
                "target": target,
                "success": result.success,
                "error": result.error,
                "duration_ms": result.duration_ms,
            },
        )
        return result

    def _system_info(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target, params
        data: dict[str, object] = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "workspace_root": str(self.workspace_root),
        }
        if os.name == "nt":
            data["memory"] = self._memory_info()
        return PcExecution(
            success=True, summary="Collected non-privileged system information.", data=data
        )

    def _memory_info(self) -> dict[str, int]:
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {}
        return {
            "total_bytes": status.ullTotalPhys,
            "available_bytes": status.ullAvailPhys,
            "load_percent": status.dwMemoryLoad,
        }

    def _list_processes(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target, params
        command = (
            ["tasklist", "/FO", "CSV", "/NH"] if os.name == "nt" else ["ps", "-eo", "pid,comm"]
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise PcHostError("process_list_failed")
        processes: list[dict[str, object]] = []
        if os.name == "nt":
            for row in csv.reader(completed.stdout.splitlines()):
                if len(row) < 5:
                    continue
                try:
                    pid = int(row[1])
                except ValueError:
                    pid = row[1]
                processes.append(
                    {
                        "image_name": row[0],
                        "pid": pid,
                        "session_name": row[2],
                        "session_number": row[3],
                        "memory_usage": row[4],
                    }
                )
        else:
            for line in completed.stdout.splitlines()[1:]:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    processes.append({"pid": parts[0], "image_name": parts[1]})
        return PcExecution(
            success=True,
            summary=f"Listed {len(processes)} processes.",
            data={"processes": processes},
        )

    def _apps_list(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        process_result = self._list_processes(target, params)
        return replace(process_result, summary="Listed running applications and processes.")

    def _apps_launch(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        executable = params.get("executable") or target
        if not isinstance(executable, str) or not executable.strip():
            raise PcHostError("executable_required")
        executable = executable.strip()
        executable_name = Path(executable).name.lower()
        if executable_name not in self.allowed_applications:
            raise PcHostError("application_not_allowlisted")
        raw_args = params.get("args", ())
        if isinstance(raw_args, str) or not isinstance(raw_args, (list, tuple)):
            raise PcHostError("args_must_be_array")
        if len(raw_args) > 8 or not all(
            isinstance(item, str) and "\x00" not in item for item in raw_args
        ):
            raise PcHostError("invalid_application_args")
        command = [executable]
        path_value = params.get("path")
        opened_path: Path | None = None
        if path_value is not None:
            if not isinstance(path_value, str):
                raise PcHostError("path_must_be_string")
            opened_path = self._resolve_path(path_value, must_exist=False)
            command.append(str(opened_path))
        command.extend(raw_args)
        try:
            process = subprocess.Popen(
                command,
                cwd=self.workspace_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError as exc:
            raise PcHostError("application_launch_failed") from exc
        return PcExecution(
            success=True,
            summary=f"Launched allowlisted application {executable_name}.",
            data={
                "pid": process.pid,
                "executable": executable_name,
                "path": str(opened_path) if opened_path else None,
            },
            reversible=True,
        )

    def _files_read(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        path = self._resolve_path(target, must_exist=True)
        if not path.is_file():
            raise PcHostError("file_required")
        max_bytes = params.get("max_bytes", 1_000_000)
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not 0 < max_bytes <= 10_000_000
        ):
            raise PcHostError("invalid_max_bytes")
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise PcHostError("file_too_large")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PcHostError("file_not_utf8") from exc
        return PcExecution(
            success=True,
            summary=f"Read {self._relative(path)}.",
            data={"path": self._relative(path), "content": content, "bytes": len(raw)},
        )

    def _files_copy(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        source = self._resolve_path(target, must_exist=True)
        destination = self._resolve_path(params.get("destination"), must_exist=False)
        if destination.exists():
            raise PcHostError("destination_exists")
        self._ensure_destination_is_not_nested(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return PcExecution(
            success=True,
            summary=f"Copied {self._relative(source)} to {self._relative(destination)}.",
            changed_files=(self._relative(destination),),
            reversible=True,
        )

    def _files_move(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        source = self._resolve_path(target, must_exist=True)
        destination = self._resolve_path(params.get("destination"), must_exist=False)
        if destination.exists():
            raise PcHostError("destination_exists")
        self._ensure_destination_is_not_nested(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return PcExecution(
            success=True,
            summary=f"Moved {self._relative(source)} to {self._relative(destination)}.",
            changed_files=(self._relative(source), self._relative(destination)),
            reversible=False,
        )

    def _files_patch(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        path = self._resolve_path(target, must_exist=True)
        if not path.is_file():
            raise PcHostError("file_required")
        replacements = params.get("replacements")
        if not isinstance(replacements, (list, tuple)) or not replacements:
            raise PcHostError("replacements_required")
        content = path.read_text(encoding="utf-8")
        for replacement in replacements:
            if not isinstance(replacement, Mapping):
                raise PcHostError("invalid_replacement")
            old = replacement.get("old")
            new = replacement.get("new")
            if not isinstance(old, str) or not old:
                raise PcHostError("replacement_old_required")
            if not isinstance(new, str):
                raise PcHostError("replacement_new_required")
            if old not in content:
                raise PcHostError("replacement_not_found")
            content = content.replace(old, new, 1)
        path.write_text(content, encoding="utf-8", newline="")
        return PcExecution(
            success=True,
            summary=f"Applied {len(replacements)} controlled replacement(s) to {self._relative(path)}.",
            changed_files=(self._relative(path),),
            reversible=True,
        )

    def _files_snapshot(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        source = self._resolve_path(target, must_exist=True)
        destination_value = params.get("destination")
        if destination_value is None:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            destination = self._resolve_path(
                f".snapshots/{source.name}-{stamp}-{uuid4().hex[:8]}",
                must_exist=False,
            )
        else:
            destination = self._resolve_path(destination_value, must_exist=False)
        if destination.exists():
            raise PcHostError("destination_exists")
        self._ensure_destination_is_not_nested(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        relative_destination = self._relative(destination)
        return PcExecution(
            success=True,
            summary=f"Created a working snapshot at {relative_destination}.",
            artifacts=(relative_destination,),
            changed_files=(relative_destination,),
            reversible=True,
        )

    def _powershell(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        script = params.get("script")
        if not isinstance(script, str) or not script.strip():
            raise PcHostError("script_required")
        self._validate_powershell_script(script)
        working_directory = self._resolve_path(
            params.get("working_directory") or self.workspace_root,
            must_exist=True,
        )
        if not working_directory.is_dir():
            raise PcHostError("working_directory_required")
        executable = shutil.which("powershell.exe") or shutil.which("pwsh")
        if executable is None:
            raise PcHostError("powershell_unavailable")
        completed = subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
            check=False,
            shell=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return PcExecution(
            success=completed.returncode == 0,
            summary="PowerShell command completed."
            if completed.returncode == 0
            else "PowerShell command failed.",
            data={"stdout": stdout, "stderr": stderr, "return_code": completed.returncode},
            logs=("powershell_command_executed",),
            warnings=(stderr,) if stderr else (),
            error=None if completed.returncode == 0 else "powershell_failed",
            reversible=False,
        )

    @staticmethod
    def _validate_powershell_script(script: str) -> None:
        if any(
            marker in script
            for marker in (
                "\n",
                "\r",
                ";",
                "|",
                "&",
                ">",
                "<",
                "`",
                "$",
                "(",
                ")",
                "{",
                "}",
                "[",
                "]",
            )
        ):
            raise PcHostError("powershell_script_not_allowlisted")
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9-]*)", script)
        if match is None:
            raise PcHostError("powershell_command_not_allowlisted")
        allowed_verbs = {
            "add-content",
            "copy-item",
            "get-childitem",
            "get-content",
            "get-date",
            "get-item",
            "get-location",
            "get-process",
            "move-item",
            "new-item",
            "set-content",
            "test-path",
        }
        if match.group(1).lower() not in allowed_verbs:
            raise PcHostError("powershell_command_not_allowlisted")
        for token in script.split():
            normalized = token.strip("\"'")
            if normalized.startswith(("\\", "/")) or ".." in normalized or ":" in normalized:
                raise PcHostError("powershell_path_not_allowlisted")

    def _window_list(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target, params
        windows = self._windows()
        return PcExecution(
            success=True,
            summary=f"Listed {len(windows)} visible windows.",
            data={"windows": windows},
        )

    def _window_focus(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        hwnd = self._find_window(params.get("hwnd"), params.get("title") or target)
        if os.name != "nt":
            raise PcHostError("unsupported_platform")
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        if not user32.SetForegroundWindow(hwnd):
            raise PcHostError("window_focus_failed")
        return PcExecution(success=True, summary=f"Focused window {hwnd}.", data={"hwnd": hwnd})

    def _apps_close(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        hwnd = self._find_window(params.get("hwnd"), params.get("title") or target)
        if os.name != "nt":
            raise PcHostError("unsupported_platform")
        if not ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0):
            raise PcHostError("window_close_failed")
        return PcExecution(
            success=True, summary=f"Sent close request to window {hwnd}.", data={"hwnd": hwnd}
        )

    def _screen_capture(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        if os.name != "nt":
            raise PcHostError("unsupported_platform")
        path_value = params.get("path") or f"artifacts/screenshots/screen-{uuid4().hex}.bmp"
        path = self._resolve_path(path_value, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        if width <= 0 or height <= 0:
            raise PcHostError("screen_dimensions_unavailable")
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        screen_dc = user32.GetDC(0)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        previous = gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not gdi32.BitBlt(
                memory_dc, 0, 0, width, height, screen_dc, 0, 0, 0x00CC0020 | 0x40000000
            ):
                raise PcHostError("screen_capture_failed")
            buffer = ctypes.create_string_buffer(width * height * 4)
            info = _bitmap_info(width, height)
            copied = gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
            if copied != height:
                raise PcHostError("screen_capture_failed")
            pixel_data = buffer.raw
            header = struct.pack("<2sIHHI", b"BM", 54 + len(pixel_data), 0, 0, 54)
            info_header = struct.pack(
                "<IiiHHIIiiII",
                40,
                width,
                -height,
                1,
                32,
                0,
                len(pixel_data),
                0,
                0,
                0,
                0,
            )
            path.write_bytes(header + info_header + pixel_data)
        finally:
            gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(0, screen_dc)
        relative = self._relative(path)
        return PcExecution(
            success=True,
            summary=f"Captured the screen to {relative}.",
            artifacts=(relative,),
            data={"path": relative, "width": width, "height": height, "format": "bmp"},
        )

    def _input_click(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        x, y = self._coordinates(params)
        self._require_windows()
        ctypes.windll.user32.SetCursorPos(x, y)
        self._send_mouse(0x0002)
        self._send_mouse(0x0004)
        return PcExecution(success=True, summary=f"Clicked at ({x}, {y}).", reversible=True)

    def _input_drag(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        start_x, start_y = self._coordinates(params, prefix="start_")
        end_x, end_y = self._coordinates(params, prefix="end_")
        self._require_windows()
        user32 = ctypes.windll.user32
        user32.SetCursorPos(start_x, start_y)
        self._send_mouse(0x0002)
        user32.SetCursorPos(end_x, end_y)
        self._send_mouse(0x0004)
        return PcExecution(
            success=True,
            summary=f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y}).",
            reversible=True,
        )

    def _input_type(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        text = params.get("text")
        if not isinstance(text, str) or not text or len(text) > 10_000:
            raise PcHostError("input_text_required")
        self._require_windows()
        inputs: list[_Input] = []
        for character in text:
            inputs.extend(
                [
                    self._keyboard_input(ord(character), 0x0004),
                    self._keyboard_input(ord(character), 0x0004 | 0x0002),
                ]
            )
        self._send_inputs(inputs)
        return PcExecution(
            success=True, summary=f"Typed {len(text)} character(s).", reversible=True
        )

    def _input_hotkey(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        keys = params.get("keys")
        if (
            isinstance(keys, str)
            or not isinstance(keys, (list, tuple))
            or not keys
            or len(keys) > 4
        ):
            raise PcHostError("hotkey_keys_required")
        self._require_windows()
        virtual_keys = [self._virtual_key(key) for key in keys]
        inputs = [self._keyboard_input(key, 0) for key in virtual_keys]
        inputs.extend(self._keyboard_input(key, 0x0002) for key in reversed(virtual_keys))
        self._send_inputs(inputs)
        return PcExecution(success=True, summary=f"Sent hotkey {'+'.join(keys)}.", reversible=True)

    def _input_scroll(self, target: str | None, params: Mapping[str, object]) -> PcExecution:
        del target
        amount = params.get("amount")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or not -20 <= amount <= 20
            or amount == 0
        ):
            raise PcHostError("scroll_amount_required")
        self._require_windows()
        self._send_mouse(0x0800, mouse_data=amount * 120)
        return PcExecution(success=True, summary=f"Scrolled by {amount} unit(s).", reversible=True)

    def _resolve_path(self, value: object, *, must_exist: bool) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise PcHostError("path_required")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        resolved = candidate.expanduser().resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PcHostError("path_outside_workspace") from exc
        if must_exist and not resolved.exists():
            raise PcHostError("path_not_found")
        return resolved

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.workspace_root).as_posix()

    @staticmethod
    def _ensure_destination_is_not_nested(source: Path, destination: Path) -> None:
        if source.is_dir():
            try:
                destination.relative_to(source)
            except ValueError:
                return
            raise PcHostError("destination_inside_source")

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

    def _windows(self) -> list[dict[str, object]]:
        if os.name != "nt":
            return []
        user32 = ctypes.windll.user32
        windows: list[dict[str, object]] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            windows.append(
                {"hwnd": int(hwnd), "title": title_buffer.value, "pid": int(process_id.value)}
            )
            return True

        user32.EnumWindows(callback_type(callback), 0)
        return windows

    def _find_window(self, hwnd_value: object, title_value: object) -> int:
        if os.name != "nt":
            raise PcHostError("unsupported_platform")
        if isinstance(hwnd_value, int) and hwnd_value > 0:
            return hwnd_value
        if isinstance(title_value, str) and title_value.strip():
            query = title_value.casefold()
            for window in self._windows():
                if query in str(window["title"]).casefold():
                    return int(window["hwnd"])
        raise PcHostError("window_not_found")

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise PcHostError("unsupported_platform")

    @staticmethod
    def _coordinates(params: Mapping[str, object], prefix: str = "") -> tuple[int, int]:
        x = params.get(f"{prefix}x")
        y = params.get(f"{prefix}y")
        if (
            isinstance(x, bool)
            or not isinstance(x, int)
            or isinstance(y, bool)
            or not isinstance(y, int)
        ):
            raise PcHostError("coordinates_required")
        if not 0 <= x <= 10000 or not 0 <= y <= 10000:
            raise PcHostError("coordinates_out_of_range")
        return x, y

    @staticmethod
    def _keyboard_input(virtual_key: int, flags: int) -> _Input:
        item = _Input()
        item.type = 1
        item.ki = _KeyboardInput(0, virtual_key, flags, 0, 0)
        return item

    @staticmethod
    def _virtual_key(key: object) -> int:
        if not isinstance(key, str) or not key:
            raise PcHostError("invalid_hotkey")
        normalized = key.upper()
        names = {
            "CTRL": 0x11,
            "CONTROL": 0x11,
            "SHIFT": 0x10,
            "ALT": 0x12,
            "WIN": 0x5B,
            "WINDOWS": 0x5B,
            "ENTER": 0x0D,
            "ESC": 0x1B,
            "ESCAPE": 0x1B,
            "TAB": 0x09,
            "SPACE": 0x20,
            "BACKSPACE": 0x08,
            "DELETE": 0x2E,
            "UP": 0x26,
            "DOWN": 0x28,
            "LEFT": 0x25,
            "RIGHT": 0x27,
        }
        if normalized in names:
            return names[normalized]
        if len(normalized) == 1 and normalized.isalnum():
            return ord(normalized)
        if (
            normalized.startswith("F")
            and normalized[1:].isdigit()
            and 1 <= int(normalized[1:]) <= 12
        ):
            return 0x70 + int(normalized[1:]) - 1
        raise PcHostError("invalid_hotkey")

    @staticmethod
    def _send_mouse(flags: int, mouse_data: int = 0) -> None:
        item = _Input()
        item.type = 0
        item.mi = _MouseInput(0, 0, mouse_data, flags, 0, 0)
        NativeWindowsPcControl._send_inputs([item])

    @staticmethod
    def _send_inputs(inputs: Sequence[_Input]) -> None:
        array_type = _Input * len(inputs)
        array = array_type(*inputs)
        sent = ctypes.windll.user32.SendInput(len(inputs), array, ctypes.sizeof(_Input))
        if sent != len(inputs):
            raise PcHostError("input_dispatch_failed")


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyboardInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _InputUnion)]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_ulong),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_ulong),
        ("biSizeImage", ctypes.c_ulong),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_ulong),
        ("biClrImportant", ctypes.c_ulong),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", ctypes.c_ulong * 3)]


def _bitmap_info(width: int, height: int) -> _BitmapInfo:
    info = _BitmapInfo()
    info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    return info
