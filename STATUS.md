# Status

## Active milestone

M3 — PC Control (complete). M4 — Permission System is the next milestone and has not started.

## What works

- The repository is connected to GitHub `origin/main`; M0 and M1 history is preserved.
- Python 3.12, editable installation, pytest, and Ruff are configured through `pyproject.toml` and `scripts/setup.ps1`.
- The local development gateway starts with `scripts/dev.ps1` and binds to `127.0.0.1` by default.
- Hermes chat uses the configured local OpenAI-compatible Qwen endpoint, with deterministic routing and structured JSON logging.
- The default local model remains `qwen3.8:27b`; the 64K operating profile and the light-task benchmark are documented.
- The gateway exposes readiness, discovery, chat, Codex, and PC routes.
- `CodexHandoffService` validates Git roots, detects stale starting revisions, requires explicit approval, invokes the configured Codex CLI in an ephemeral workspace-write sandbox, observes dirty files, runs an optional argv test command without a shell, and returns a structured summary.
- Codex handoffs are retained in a process-local `/api/v1/codex/runs` list. They do not commit or push changes.
- `PcIntegration` exposes structured M3 actions for system/process inspection, allowlisted application launch/focus/close, workspace-bounded file read/copy/move/patch/snapshot, restricted PowerShell, window enumeration/focus, BMP screen capture, and Windows keyboard/mouse fallback input.
- PC mutations and disruptive operations use explicit level-2 `approval_granted: true`; the provider never elevates and does not offer unrestricted shell or process control.
- Blender and SC2 remain safe non-controlling skeletons.
- The opt-in `scripts/pc-acceptance.ps1` exercises Notepad launch, window focus, known text input, save, read-back verification, and close. Normal automated tests never open a GUI application.

## Intentionally not implemented

- The full M4 approval service, durable policy store, allowlist administration, and constrained privileged helper.
- Hermes conversation history, persistent memory, streaming, authentication, and the web UI/PWA.
- LangGraph execution, durable persistence, checkpoints, retries, pause/resume/cancel, and event storage.
- Blender bpy/MCP/CLI control, rendering, and scene workflows.
- SC2 project parsing, structured modification, Galaxy tooling, launching, and packaging.
- Remote access, public raw agent services, evaluator, and skill promotion.

## Known limitations

- The gateway is still a minimal standard-library development server, not a production API server.
- Codex execution requires a locally installed and authenticated `codex` CLI. The automated suite uses a fake backend and does not invoke a live coding agent.
- Codex handoff and workflow records are process-local and disappear on restart; no event store or durable checkpoint exists yet.
- PC application launch is intentionally limited to the configured executable-name allowlist. The default allowlist is `notepad.exe`, `calc.exe`, and `mspaint.exe`.
- PC file operations are constrained to `PERSONAL_AI_PC_WORKSPACE_ROOT`, which defaults to the gateway working directory. PowerShell is deliberately narrow and is not a general command runner.
- The live Notepad acceptance requires an interactive Windows desktop and is not run automatically because it changes host GUI state.
- The main service remains non-administrator; privileged actions are rejected until M4 defines the helper boundary.

## Verification

The latest verification uses Python 3.12.0 on Windows.

- `scripts/check.ps1`: passed — Ruff format, Ruff lint, and 29 tests passed in 1.85 seconds.
- `python -m personal_ai.dev --check`: passed — gateway, workflows, Hermes/Qwen, Codex CLI, controlled PC, Blender skeleton, and SC2 skeleton all reported ready/ok.
- M2 fake acceptance: passed — a Git fixture was changed by the fake Codex backend, the dirty file was reported, and the post-handoff test passed.
- M3 file/policy acceptance: passed — read, copy, patch, workspace escape rejection, approval gating, PowerShell chaining rejection, and capability discovery are covered by tests.
- Live Notepad acceptance: available through `scripts/pc-acceptance.ps1`, not run in this cycle.
