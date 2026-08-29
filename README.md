# Personal AI Platform

This repository is the persistent handoff point for the local-first Personal AI Platform described in [`MasterPlan/MasterPlan.md`](MasterPlan/MasterPlan.md).

The repository now contains the bounded implementation through the M18 Secure Remote Access foundation. The Python runtime remains dependency-light on the Windows host. Codex handoffs, Blender/SC2 mutations, and destructive PC actions use centrally configured, scoped, expiring, one-time approvals. The main process remains non-administrator and the privileged-helper boundary fails closed. Live Blender/SC2 application validation is environment-dependent; GUI automation and game/editor launching remain disabled.

## Quick start on Windows

From PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\check.ps1
.\scripts\dev.ps1
.\scripts\web.ps1
```

The durable runner is graph-compatible without requiring LangGraph for the local baseline. Install the optional adapter dependency when evaluating it:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,workflow]"
```

The development gateway binds to `127.0.0.1:8000` by default. Check `http://127.0.0.1:8000/health` or use `.\.venv\Scripts\python.exe -m personal_ai.dev --check`. Ollama is the configured local Qwen backend; start it and ensure `qwen3.8:27b` is installed before sending chat requests:

```powershell
ollama pull qwen3.8:27b
ollama list
```

Hermes Agent is installed separately in the user profile by the official Windows installer. Its profile is configured for the same local endpoint and model.

Example chat request:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"message":"Hello","task_type":"general"}'
```

Example Codex handoff approval flow (the first call returns HTTP 409 plus an approval object):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/codex/handoff `
  -ContentType "application/json" `
  -Body '{"repository_path":"D:/work/repository","task":"Implement the requested change","test_command":["py","-m","pytest","-q"]}'
```

Accept the returned `approval_id` with `POST /api/v1/approvals/{approval_id}/accept`, then repeat the exact handoff payload with that `approval_id`. Approvals expire after five minutes by default, are bound to the exact action/target/parameters, and can be consumed only once.

The gateway routes this explicit coding handoff through Hermes's `delegate_to_codex` boundary before the central permission check reaches Codex.

Example read-only PC operation:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/pc/invoke `
  -ContentType "application/json" `
  -Body '{"action":"pc.system_info","parameters":{}}'
```

The restricted PowerShell operation uses a structured verb and argument array; free-form scripts are rejected:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/pc/invoke `
  -ContentType "application/json" `
  -Body '{"action":"pc.shell.powershell","parameters":{"verb":"Get-ChildItem","args":["-Path","."]}}'
```

Run the opt-in Notepad acceptance only when the local gateway is running and GUI interaction is wanted:

```powershell
.\scripts\pc-acceptance.ps1
```

Environment overrides use the `PERSONAL_AI_` prefix. Supported values include `HOST`, `PORT`, `ENVIRONMENT`, `LOG_LEVEL`, `ALLOW_REMOTE`, `API_TOKEN`, `ALLOWED_ORIGINS`, `ALLOWED_CLIENT_NETWORKS`, the Qwen and Codex settings, `PERMISSION_POLICY_PATH`, the PC settings, `BLENDER_EXECUTABLE`, `BLENDER_COMMAND_TIMEOUT_SECONDS`, `SC2_WORKSPACE_ROOT`, `ARTIFACT_ROOT`, `MEMORY_ROOT`, and `WORKFLOW_STORAGE_ROOT`. Tool levels and allowlists live in the validated permission policy, not environment variables. Remote binding is disabled by default.

## M5-M18 local platform

The gateway exposes structured Blender and SC2 provider boundaries at `/api/v1/blender/invoke` and `/api/v1/sc2/invoke`. Blender uses background CLI execution when `PERSONAL_AI_BLENDER_EXECUTABLE` is available and supports JSON scene fixtures for deterministic development. SC2 works with bounded project directories and ZIP-compatible working copies. Both integrations preserve sources and require central approval for mutations.

Durable workflow runs are available through `/api/v1/workflows`, `/api/v1/runs`, and the run control endpoints. Checkpoints and event history are stored under `artifacts/workflows/`; run event replay is also available as an SSE stream at `/api/v1/runs/{id}/events/stream`. Artifact metadata and downloads are exposed beneath `/api/v1/artifacts` and remain bounded to the configured artifact root. Semantic, episodic, and procedural memory is stored under `memory/`; repeated successful procedures can create unpromoted candidate skills, while explicit validation and promotion remain required.

When `PERSONAL_AI_API_TOKEN` is set, the HTTP adapter requires a bearer token. Remote binding refuses to start without one or a valid non-empty `PERSONAL_AI_ALLOWED_CLIENT_NETWORKS` CIDR list. Browser origins must be listed in `PERSONAL_AI_ALLOWED_ORIGINS`, and browser write requests must include `X-Personal-AI-CSRF` matching the configured token. Keep the default loopback binding for local development. For a future Tailscale deployment, explicitly add the approved tailnet CIDR (for example `100.64.0.0/10`) and keep upstream Ollama, Hermes, Blender, SC2, Codex, and privileged-helper services off the network.

## Handoff documents

Future agents should read these files before making changes:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current boundaries and target direction;
- [`STATUS.md`](STATUS.md) — what was verified in the latest cycle;
- [`NEXT.md`](NEXT.md) — bounded next tasks;
- [`DECISIONS.md`](DECISIONS.md) — architectural decisions;
- [`TOOL_CONTRACTS.md`](TOOL_CONTRACTS.md) — structured contracts and safety boundaries;
- [`ROADMAP.md`](ROADMAP.md) — milestone status.

Future agents should read the handoff documents and continue with the bounded next task in `NEXT.md`; do not assume live Blender, SC2 runtime, or LangGraph execution is available.
