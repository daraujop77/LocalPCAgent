# Status

## Active milestone

M0 — Foundation (complete for this development cycle).

## What works

- The repository is initialized as a Git repository and contains the plan-defined monorepo directories.
- Python 3.12 project metadata is declared in `pyproject.toml` with an editable-install development extra for pytest and Ruff.
- Safe environment-backed settings default to `127.0.0.1:8000`, development mode, INFO logging, and remote access disabled.
- Standard-library JSON-line logging is available.
- `HealthStatus`, `ToolResult`, and `ToolProvider` define shared structured contracts.
- The gateway starts locally and provides `GET /`, `/health`, `/health/live`, `/health/ready`, `/api/v1/health`, `/api/v1/tools`, and `/api/v1/runs`.
- Gateway health reports the gateway, workflow boundary, PC skeleton, Blender skeleton, and SC2 skeleton.
- PC, Blender, and SC2 providers advertise future capability names but do not perform any control or mutation.
- All M0 gateway HTTP routes are read-only; mutating HTTP methods are rejected.
- PowerShell setup, development-start, and check scripts are present.
- Initial unit and gateway integration tests exist.

## Intentionally not implemented

- Hermes conversational agent or local Qwen connection.
- LangGraph execution, durable persistence, checkpoints, retries, approvals, or event storage.
- Real Windows PC control, shell execution, filesystem mutation, keyboard/mouse input, or screenshots.
- Blender `bpy`/MCP/CLI control or rendering.
- SC2 map/mod parsing, patching, Galaxy tooling, launching, or packaging.
- Web UI, public/remote access, privileged helper, model routing, evaluator, memory, or skill promotion.

## Known limitations

- The project has no configured remote Git origin.
- The gateway is a minimal standard-library development server, not a production API server.
- Workflow state is process-local and empty on restart.
- The integration capability catalog is descriptive only; it is not an execution API.

## Verification

The latest verification was run on 2026-08-29 using Python 3.12.0 on Windows:

- `.\.venv\Scripts\python.exe -m ruff format --check .`: passed — 40 files already formatted.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed — all checks passed.
- `.\.venv\Scripts\python.exe -m pytest`: passed — 7 tests passed in 0.06s.
- `.\.venv\Scripts\python.exe -m personal_ai.dev --check`: passed — all five health checks reported ready.
- `.\.venv\Scripts\python.exe -m personal_ai.dev` plus `GET http://127.0.0.1:8000/health`: passed — HTTP 200 and JSON status `ok`.
- `.\scripts\check.ps1`: passed — formatting, linting, and 7 tests passed in 0.04s.

The exact combined check command remains available as `.\scripts\check.ps1` after the M0 environment is installed.
