# Personal AI Platform

This repository is the persistent handoff point for the local-first Personal AI Platform described in [`MasterPlan/MasterPlan.md`](MasterPlan/MasterPlan.md).

The repository now contains M0 — Foundation and M1 — Local AI. The Python runtime is intentionally small and dependency-light on the Windows host. M1 provides a Hermes conversational boundary, deterministic routing, and an OpenAI-compatible local Qwen client. It does not yet include Codex delegation, LangGraph durability, Blender/SC2 automation, or unrestricted PC control.

## Quick start on Windows

From PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\check.ps1
.\scripts\dev.ps1
```

The development gateway binds to `127.0.0.1:8000` by default. Check `http://127.0.0.1:8000/health` or use `.\.venv\Scripts\python.exe -m personal_ai.dev --check`. Start a compatible local Qwen server at `http://127.0.0.1:11434/v1` (the default) before sending chat requests.

Example chat request:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"message":"Hello","task_type":"general"}'
```

Environment overrides use the `PERSONAL_AI_` prefix. Supported values are `HOST`, `PORT`, `ENVIRONMENT`, `LOG_LEVEL`, `ALLOW_REMOTE`, `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_TIMEOUT_SECONDS`, `QWEN_HEALTH_TIMEOUT_SECONDS`, and `QWEN_API_KEY`. Remote binding is disabled by default. A local API key is optional and is never logged.

## Handoff documents

Future agents should read these files before making changes:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current boundaries and target direction;
- [`STATUS.md`](STATUS.md) — what was verified in the latest cycle;
- [`NEXT.md`](NEXT.md) — bounded next tasks;
- [`DECISIONS.md`](DECISIONS.md) — architectural decisions;
- [`TOOL_CONTRACTS.md`](TOOL_CONTRACTS.md) — structured contracts and safety boundaries;
- [`ROADMAP.md`](ROADMAP.md) — milestone status.

Do not begin M2 unless explicitly instructed.
