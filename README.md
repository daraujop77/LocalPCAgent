# Personal AI Platform

This repository is the persistent handoff point for the local-first Personal AI Platform described in [`MasterPlan/MasterPlan.md`](MasterPlan/MasterPlan.md).

The repository currently contains M0 — Foundation only. The Python runtime is intentionally small and dependency-light on the Windows host. It provides configuration, structured logging, tool/result contracts, service health checks, and safe integration boundaries. It does not yet connect Hermes, Qwen, LangGraph, Blender, SC2, or unrestricted PC control.

## Quick start on Windows

From PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\check.ps1
.\scripts\dev.ps1
```

The development gateway binds to `127.0.0.1:8000` by default. Check `http://127.0.0.1:8000/health` or use `.\.venv\Scripts\python.exe -m personal_ai.dev --check`.

Environment overrides use the `PERSONAL_AI_` prefix. Supported values are `HOST`, `PORT`, `ENVIRONMENT`, `LOG_LEVEL`, and `ALLOW_REMOTE`. Remote binding is disabled by default.

## Handoff documents

Future agents should read these files before making changes:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current boundaries and target direction;
- [`STATUS.md`](STATUS.md) — what was verified in the latest cycle;
- [`NEXT.md`](NEXT.md) — bounded next tasks;
- [`DECISIONS.md`](DECISIONS.md) — architectural decisions;
- [`TOOL_CONTRACTS.md`](TOOL_CONTRACTS.md) — structured contracts and safety boundaries;
- [`ROADMAP.md`](ROADMAP.md) — milestone status.

Do not begin M1 unless explicitly instructed.

