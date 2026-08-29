# Personal AI Platform

This repository is the persistent handoff point for the local-first Personal AI Platform described in [`MasterPlan/MasterPlan.md`](MasterPlan/MasterPlan.md).

The repository now contains M0 — Foundation, M1 — Local AI, M2 — Codex Integration, and M3 — PC Control. The Python runtime is intentionally small and dependency-light on the Windows host. M2 provides an explicit, observable Codex repository handoff. M3 provides allowlisted, workspace-bounded Windows operations. LangGraph durability, Blender/SC2 automation, the full permission service, and unrestricted PC control remain future work.

## Quick start on Windows

From PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\check.ps1
.\scripts\dev.ps1
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

Example approved Codex handoff:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/codex/handoff `
  -ContentType "application/json" `
  -Body '{"repository_path":"D:/work/repository","task":"Implement the requested change","test_command":["py","-m","pytest","-q"],"approval_granted":true}'
```

Example read-only PC operation:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/pc/invoke `
  -ContentType "application/json" `
  -Body '{"action":"pc.system_info","parameters":{}}'
```

Run the opt-in Notepad acceptance only when the local gateway is running and GUI interaction is wanted:

```powershell
.\scripts\pc-acceptance.ps1
```

Environment overrides use the `PERSONAL_AI_` prefix. Supported values are `HOST`, `PORT`, `ENVIRONMENT`, `LOG_LEVEL`, `ALLOW_REMOTE`, `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_TIMEOUT_SECONDS`, `QWEN_HEALTH_TIMEOUT_SECONDS`, `QWEN_API_KEY`, `CODEX_EXECUTABLE`, `CODEX_TIMEOUT_SECONDS`, `PC_WORKSPACE_ROOT`, `PC_ALLOWED_APPLICATIONS`, and `PC_COMMAND_TIMEOUT_SECONDS`. Remote binding is disabled by default. A local API key is optional and is never logged.

## Handoff documents

Future agents should read these files before making changes:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current boundaries and target direction;
- [`STATUS.md`](STATUS.md) — what was verified in the latest cycle;
- [`NEXT.md`](NEXT.md) — bounded next tasks;
- [`DECISIONS.md`](DECISIONS.md) — architectural decisions;
- [`TOOL_CONTRACTS.md`](TOOL_CONTRACTS.md) — structured contracts and safety boundaries;
- [`ROADMAP.md`](ROADMAP.md) — milestone status.

Future agents should continue with the bounded tasks in `NEXT.md`; do not begin M4 without explicit instruction.
